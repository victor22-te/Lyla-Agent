import os
import time
import subprocess
import threading
import struct
import math
from pathlib import Path
from typing import Callable, Optional

class HotwordDetector:
    """
    Detector de Hotword nativo y liviano para LYLA (Spider-Man 2099).
    Monitorea el micrófono usando PipeWire (pw-record) y cuando detecta voz
    evalúa si se pronunció 'oye lyla', 'oye laila', 'lyla' o 'laila'
    usando la API ultrarrápida de Groq Whisper o Gemini.
    Zero local CPU / 100% Cloud-First & Native PipeWire.
    """
    def __init__(self, agent, on_wake: Callable[[], None]):
        self.agent = agent
        self.on_wake = on_wake
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_active_dialog = False
        self.temp_dir = Path("/tmp/lyla_hotword")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.wake_words = ["oye lyla", "oye laila", "hola lyla", "hola laila", "hey lyla", "lyla", "laila"]

    def set_dialog_state(self, in_dialog: bool):
        """Si la HUD está en medio de una grabación o reproduciendo TTS, se pausa el detector."""
        self._is_active_dialog = in_dialog

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _listen_loop(self):
        env = os.environ.copy()
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

        chunk_file = self.temp_dir / "hw_chunk.wav"

        while self._running:
            if self._is_active_dialog:
                time.sleep(0.3)
                continue

            try:
                if chunk_file.exists():
                    try:
                        chunk_file.unlink()
                    except Exception:
                        pass

                # Graba fragmentos rápidos de 2.2 segundos para detectar la palabra clave
                proc = subprocess.Popen(
                    [
                        "pw-record",
                        "--rate", "16000",
                        "--channels", "1",
                        "--format", "s16",
                        str(chunk_file)
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env
                )

                time_waited = 0.0
                while time_waited < 2.2 and self._running and not self._is_active_dialog:
                    time.sleep(0.1)
                    time_waited += 0.1

                try:
                    proc.terminate()
                    proc.wait(timeout=0.8)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

                if self._is_active_dialog or not self._running:
                    continue

                if chunk_file.exists() and chunk_file.stat().st_size > 8000:
                    # Análisis de energía rápido (VAD simple para no gastar API innecesariamente)
                    with open(chunk_file, "rb") as f:
                        f.seek(44) # Saltar encabezado WAV
                        raw_data = f.read(16000 * 2) # 1 segundo
                        if len(raw_data) >= 1000:
                            count = len(raw_data) // 2
                            samples = struct.unpack(f"<{count}h", raw_data[:count*2])
                            rms = math.sqrt(sum(s * s for s in samples) / count)
                            # Si hay silencio absoluto, continuar
                            if rms < 250:
                                continue

                    # Transcribir en la nube (Groq Whisper tarda < 0.25 segundos)
                    text = self.agent.stt.transcribe(chunk_file).lower().strip()
                    if text:
                        # Limpiar signos de puntuación
                        clean_text = "".join(c for c in text if c.isalnum() or c.isspace()).strip()
                        # Comprobar si coincide con alguna de las palabras clave
                        matched = any(w in clean_text for w in self.wake_words)
                        if matched:
                            # Notificar al HUD que despierte
                            if callable(self.on_wake):
                                self.on_wake()
                            time.sleep(1.0)
            except Exception:
                time.sleep(0.5)
