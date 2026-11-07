import re
from typing import Optional
from .config import Config
from .tracker import ResourceTracker
from ..memory.manager import MemoryManager
from ..providers.router import LLMRouter
from ..audio.tts import CloudTTS
from ..audio.stt import CloudSTT
from ..audio.capture import AudioCapture

class LylaAgent:
    """
    LYLA Engine (Spider-Man 2099 Asistente Holográfico Autónomo).
    Coordina memoria sólida híbrida, llamadas cloud a LLMs, síntesis/captura de audio y proactividad.
    """
    def __init__(self):
        self.config = Config()
        self.tracker = ResourceTracker()
        self.memory = MemoryManager(
            config_dir=self.config.declarative_path,
            db_path=self.config.episodic_db_path,
            max_turns=self.config.max_session_history
        )
        self.router = LLMRouter(self.config, self.tracker)
        self.tts = CloudTTS(voice=self.config.tts_voice, output_dir=self.config.temp_audio_dir)
        self.stt = CloudSTT(self.config)
        self.capture = AudioCapture(self.config.temp_audio_dir)

    def process_message(self, user_text: str, voice_reply: bool = False) -> str:
        """
        Procesa el mensaje de Víctor:
        1. Inyecta memoria declarativa + episódica en el prompt.
        2. Obtiene respuesta del router LLM.
        3. Verifica si hay sugerencias proactivas ("Oye Víctor...").
        4. Registra en memoria de sesión y detecta si hay que guardar un recuerdo en SQLite.
        5. Reproduce respuesta por voz si voice_reply está activo.
        """
        system_prompt = self.memory.build_system_prompt(user_text)
        history = self.memory.session.get_history()

        # Generar respuesta con LLM
        reply_text, provider_used = self.router.generate(
            system_prompt=system_prompt,
            history=history,
            user_message=user_text
        )

        # Evaluar proactividad ("Oye Víctor...")
        proactive_advice = self.tracker.check_proactive_advice()
        if proactive_advice:
            advice_str = "\n\n💡 " + "\n💡 ".join(proactive_advice)
            reply_text += advice_str

        # Registrar en memoria de sesión
        self.memory.record_interaction(user_text, reply_text)

        # Detectar si Víctor compartió un hecho importante para guardarlo en Capa 2 (SQLite)
        self._auto_detect_memory(user_text, reply_text)

        # Reproducir voz si está habilitado
        if voice_reply and self.config.audio_enabled:
            # Limpiar emojis o Markdown pesado antes del TTS para que suene fluido
            clean_speech = re.sub(r'[*_#`💡]', '', reply_text)
            self.tts.speak(clean_speech, play_audio=True)

        return reply_text

    def _auto_detect_memory(self, user_text: str, reply_text: str):
        """
        Detecta patrones clave para consolidar en memoria episódica automáticamente
        (e.g., 'recuerda que...', 'mi proyecto es...', 'prefiero...').
        """
        user_lower = user_text.lower()
        if "recuerda que" in user_lower or "anota que" in user_lower or "no olvides que" in user_lower:
            fact = user_text
            for prefix in ["recuerda que", "anota que", "no olvides que"]:
                if prefix in user_lower:
                    idx = user_lower.find(prefix) + len(prefix)
                    fact = user_text[idx:].strip()
                    break
            self.memory.consolidate_memory(
                category="fact",
                summary=fact,
                details=f"Petición directa de Víctor: {user_text}",
                tags="recuerdo,preferencia",
                importance=4
            )
            print(f"\n🧠 [Memoria Sólida] Se ha guardado en SQLite: '{fact}'")

    def remember(self, category: str, summary: str, details: str = "", tags: str = "", importance: int = 1):
        """Método explícito para almacenar un hecho en la memoria episódica."""
        return self.memory.consolidate_memory(category, summary, details, tags, importance)
