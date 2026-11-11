"""
Detector de Hotword para LYLA (v2).

Por qué el v1 fallaba ("a veces sí, a veces no"):
- Grababa pedazos fijos de 2.2s y los transcribía: si "oye lyla" caía en el
  corte entre dos pedazos, ningún pedazo traía la frase completa y no despertaba.
- El VAD solo revisaba el PRIMER segundo de cada pedazo: si Víctor hablaba en
  la segunda mitad, el pedazo se descartaba como silencio.
- Mientras transcribía (llamada a la nube), el micrófono NO grababa: punto
  ciego en el que se perdía todo lo dicho.
- El matching era substring exacto: Whisper transcribe "lyla" como "laila",
  "lila", "leila" o "oíla", y ninguna coincidía.

Cómo funciona v2:
- Grabación CONTINUA con pw-cat (PipeWire) en raw PCM a un buffer circular
  en RAM (sin archivos que crezcan, sin reiniciar el grabador).
- Ventanas SOLAPADAS de 3s evaluadas cada 1s: cualquier frase de hasta 2s
  queda completa en al menos una ventana (solapamiento de 2s).
- El VAD revisa el segundo MÁS RECIENTE de cada ventana (toda la línea de
  tiempo queda cubierta), y el micrófono nunca deja de grabar mientras se
  transcribe (el transcriptor lee del buffer, no del micrófono).
- Matching difuso: normaliza acentos/puntuación y acepta las variantes con
  las que Whisper suele transcribir "lyla", más un respaldo por similitud
  para transcripciones cortas.

El grabador es pw-cat (PipeWire). Si no está, usa pw-record con los mismos
argumentos. Si no hay ninguno, el detector se desactiva con un aviso.
"""
import difflib
import math
import os
import re
import shutil
import struct
import subprocess
import threading
import time
import unicodedata
import wave
from pathlib import Path
from typing import Callable, Optional

SAMPLE_RATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE

# Ventana de análisis (3s) y paso entre evaluaciones (1s): solapamiento de 2s.
# Cualquier frase de hasta 2s ("oye lyla" dura ~1s) queda completa en al menos una ventana.
WINDOW_SECONDS = 3.0
STEP_SECONDS = 1.0
# Cuánto audio se guarda en el buffer circular (un poco más que la ventana).
RING_SECONDS = 4.0
WINDOW_BYTES = int(WINDOW_SECONDS * BYTES_PER_SECOND)
RING_BYTES = int(RING_SECONDS * BYTES_PER_SECOND)
NEWEST_SLICE_BYTES = int(1.0 * BYTES_PER_SECOND)

VAD_RMS_THRESHOLD = 250
WAKE_COOLDOWN_SECONDS = 1.0
RECORDER_RESTART_DELAY = 0.5

WAKE_WORDS = ["oye lyla", "oye laila", "hola lyla", "hola laila", "hey lyla", "hey laila", "lyla", "laila"]

# Regex de activación sobre el texto normalizado. Acepta las variantes con las
# que Whisper transcribe "lyla" (laila/layla/leila) y "oye lyla" pegado ("oila").
# "lila" solo cuenta precedida de oye/hola/hey (sola es un color, no un nombre).
_WAKE_RE = re.compile(
    r"(oye|hola|hey)\s+(lyla|laila|layla|leila|lila|oila)"
    r"|\b(lyla|laila|layla|leila|oila)\b"
)


def _normalize_text(text: str) -> str:
    """Minúsculas, sin acentos ni puntuación, espacios colapsados."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def matches_wake_word(text: str) -> bool:
    """True si la transcripción contiene el hotword (con variantes de Whisper)."""
    norm = _normalize_text(text)
    if not norm:
        return False
    if _WAKE_RE.search(norm):
        return True
    # Respaldo difuso para transcripciones cortas con errores de Whisper.
    if len(norm) <= 25:
        for w in WAKE_WORDS:
            if difflib.SequenceMatcher(None, norm, w).ratio() >= 0.85:
                return True
    return False


def _rms(pcm_bytes: bytes) -> float:
    """Energía (RMS) de un bloque PCM s16 mono."""
    if len(pcm_bytes) < 2:
        return 0.0
    count = len(pcm_bytes) // 2
    samples = struct.unpack(f"<{count}h", pcm_bytes[: count * 2])
    return math.sqrt(sum(s * s for s in samples) / count)


class HotwordDetector:
    """
    Detector de Hotword nativo y liviano para LYLA.
    Monitorea el micrófono en continuo con PipeWire (pw-cat) y cuando detecta
    voz evalúa si se pronunció 'oye lyla' (con sus variantes) usando la API
    ultrarrápida de Groq Whisper o Gemini.
    Zero local CPU / 100% Cloud-First & Native PipeWire.
    """
    def __init__(self, agent, on_wake: Callable[[], None], transcribe_fn: Optional[Callable] = None):
        self.agent = agent
        self.on_wake = on_wake
        # transcribe_fn opcional (para tests): recibe un Path WAV y devuelve texto.
        self._transcribe_fn = transcribe_fn
        self._running = False
        self._recorder_thread: Optional[threading.Thread] = None
        self._eval_thread: Optional[threading.Thread] = None
        self._recorder_proc: Optional[subprocess.Popen] = None
        self._is_active_dialog = False
        self._ring = bytearray()
        self._ring_lock = threading.Lock()
        self.temp_dir = Path("/tmp/lyla_hotword")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._window_file = self.temp_dir / "hw_window.wav"
        self.wake_words = list(WAKE_WORDS)

    def set_dialog_state(self, in_dialog: bool):
        """Si la HUD está en medio de una grabación o reproduciendo TTS, se pausa el detector."""
        was_active = self._is_active_dialog
        self._is_active_dialog = in_dialog
        if was_active and not in_dialog:
            # Al terminar el diálogo, descartar el audio viejo del buffer para
            # no evaluar (y posiblemente despertar con) lo ya conversado.
            self._clear_ring()

    def start(self):
        if self._running:
            return
        self._running = True
        self._recorder_thread = threading.Thread(target=self._record_loop, daemon=True)
        self._recorder_thread.start()
        self._eval_thread = threading.Thread(target=self._eval_loop, daemon=True)
        self._eval_thread.start()

    def stop(self):
        self._running = False
        proc = self._recorder_proc
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._recorder_proc = None

    def feed_pcm(self, data: bytes):
        """Añade PCM crudo (s16 mono 16kHz) al buffer circular. Lo usa el grabador (y los tests)."""
        if not data:
            return
        with self._ring_lock:
            self._ring.extend(data)
            if len(self._ring) > RING_BYTES:
                del self._ring[: len(self._ring) - RING_BYTES]

    def _clear_ring(self):
        with self._ring_lock:
            self._ring.clear()

    def _snapshot_window(self) -> Optional[bytes]:
        """Los últimos WINDOW_SECONDS de audio del buffer (None si aún no hay suficiente)."""
        with self._ring_lock:
            if len(self._ring) < WINDOW_BYTES:
                return None
            return bytes(self._ring[-WINDOW_BYTES:])

    def _build_recorder_cmd(self):
        """pw-cat (o pw-record) en raw PCM por stdout. Sin archivos, sin WAV."""
        if shutil.which("pw-cat"):
            base = ["pw-cat", "--record", "--raw"]
        elif shutil.which("pw-record"):
            base = ["pw-record", "--raw"]
        else:
            raise FileNotFoundError("pw-cat/pw-record no encontrado (PipeWire)")
        return base + [
            "--rate", str(SAMPLE_RATE),
            "--channels", str(CHANNELS),
            "--format", "s16",
            "-",
        ]

    def _record_loop(self):
        """Grabación continua: lee PCM crudo del stdout de pw-cat al buffer circular."""
        env = os.environ.copy()
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
        try:
            cmd = self._build_recorder_cmd()
        except FileNotFoundError as e:
            print(f"[Hotword] {e}; detector desactivado.")
            return
        while self._running:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    env=env,
                )
                self._recorder_proc = proc
                while self._running:
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        break
                    self.feed_pcm(chunk)
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            except Exception as e:
                print(f"[Hotword] Grabador falló: {e}")
            self._recorder_proc = None
            if self._running:
                time.sleep(RECORDER_RESTART_DELAY)

    def _transcribe_window(self, pcm: bytes) -> str:
        """Transcribe una ventana de audio (PCM crudo) con el STT en la nube."""
        try:
            with wave.open(str(self._window_file), "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(BYTES_PER_SAMPLE)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm)
        except Exception as e:
            print(f"[Hotword] No se pudo escribir la ventana de audio: {e}")
            return ""
        try:
            if self._transcribe_fn is not None:
                return (self._transcribe_fn(self._window_file) or "").strip()
            return (self.agent.stt.transcribe(self._window_file) or "").strip()
        except Exception as e:
            print(f"[Hotword] Transcripción falló: {e}")
            return ""

    def _eval_loop(self):
        """Evalúa ventanas solapadas de 3s cada 1s. El micrófono nunca se pausa."""
        while self._running:
            if self._is_active_dialog:
                time.sleep(0.3)
                continue
            time.sleep(STEP_SECONDS)
            if self._is_active_dialog or not self._running:
                continue
            try:
                window = self._snapshot_window()
                if window is None:
                    continue
                # VAD: energía en el segundo MÁS RECIENTE de la ventana.
                # (Antes solo se revisaba el primer segundo del pedazo.)
                if _rms(window[-NEWEST_SLICE_BYTES:]) < VAD_RMS_THRESHOLD:
                    continue
                text = self._transcribe_window(window)
                if text and matches_wake_word(text):
                    # Descartar el audio ya evaluado para no despertar dos veces
                    # con la misma frase en la siguiente ventana solapada.
                    self._clear_ring()
                    if callable(self.on_wake):
                        self.on_wake()
                    time.sleep(WAKE_COOLDOWN_SECONDS)
            except Exception as e:
                print(f"[Hotword] Error evaluando ventana: {e}")
                time.sleep(0.5)
