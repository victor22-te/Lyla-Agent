import re
from typing import Optional
from .config import Config
from .tracker import ResourceTracker
from ..memory.manager import MemoryManager
from ..providers.router import LLMRouter
from ..audio.tts import CloudTTS
from ..audio.stt import CloudSTT
from ..audio.capture import AudioCapture
from ..tools.calendar import CalendarManager

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
        self.calendar = CalendarManager(
            config_dir=self.config.declarative_path,
            db_path=self.config.episodic_db_path
        )

    def _build_runtime_context(self) -> str:
        """Inyecta el estado real en vivo (modelo activo, tokens reales y agenda) en el prompt."""
        active_provider, active_model = self.router.get_active_model()
        stats = self.tracker.get_summary()
        avail = ", ".join(f"{o['provider']}:{o['model']}" for o in self.router.get_available_models())
        cal_ctx = self.calendar.get_prompt_context()
        return (
            "\n\n---\n\n"
            "### Estado en Tiempo Real del Sistema (Runtime Actual — Usa SIEMPRE estos datos reales si Víctor pregunta):\n"
            f"- Proveedor y Modelo LLM ACTIVO en este instante: **{active_provider} ({active_model})**\n"
            f"- Modelos disponibles para cambiar con `/model`: {avail}\n"
            f"- Tokens reales consumidos en esta sesión: {stats['total_tokens_in']} entrada / {stats['total_tokens_out']} salida ({stats['total_tokens']} totales)\n"
            f"- Llamadas reales por proveedor en esta sesión: {stats['calls_by_provider']}\n"
            f"- Tiempo de sesión activa: {stats['uptime_seconds']}s\n\n"
            f"{cal_ctx}\n"
            "- Si Víctor te pide agendar/crear un evento en su calendario durante la conversación, incluye al final de tu respuesta la etiqueta exacta: "
            "`[CALENDAR_ADD: Título del evento | YYYY-MM-DD HH:MM]`."
        )

    def process_message(self, user_text: str, voice_reply: bool = False) -> str:
        """
        Procesa el mensaje de Víctor:
        1. Inyecta memoria declarativa + episódica + estado en tiempo real en el prompt.
        2. Obtiene respuesta del router LLM.
        3. Verifica si hay sugerencias proactivas ("Oye Víctor...").
        4. Registra en memoria de sesión y detecta si hay que guardar un recuerdo o evento.
        5. Reproduce respuesta por voz si voice_reply está activo.
        """
        system_prompt = self.memory.build_system_prompt(user_text) + self._build_runtime_context()
        history = self.memory.session.get_history()

        # Generar respuesta con LLM
        reply_text, provider_used = self.router.generate(
            system_prompt=system_prompt,
            history=history,
            user_message=user_text
        )

        # Detectar si LYLA emitió una etiqueta [CALENDAR_ADD: titulo | fecha_hora]
        reply_text = self._handle_calendar_tags(reply_text)

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
            self.speak_reply(reply_text)

        return reply_text

    def speak_reply(self, reply_text: str):
        """Limpia Markdown/emojis y reproduce la respuesta por voz si el audio está habilitado."""
        if self.config.audio_enabled:
            clean_speech = re.sub(r'[*_#`💡]', '', reply_text)
            self.tts.speak(clean_speech, play_audio=True)

    def _handle_calendar_tags(self, reply_text: str) -> str:
        """Detecta y ejecuta etiquetas [CALENDAR_ADD: titulo | fecha_hora] generadas por LYLA."""
        pattern = r"\[CALENDAR_ADD:\s*([^|\]]+?)\s*\|\s*([^\]]+?)\s*\]"
        matches = re.findall(pattern, reply_text)
        for title, dt_str in matches:
            ev = self.calendar.add_event(title=title.strip(), start_time=dt_str.strip())
            print(f"\n📅 [Calendario] Evento agendado: '{ev['title']}' → {ev['start_time']} ({ev['source']})")
        return re.sub(pattern, "", reply_text).strip()

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
