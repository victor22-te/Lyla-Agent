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
from ..tools.system import SystemTools

class LylaAgent:
    """
    LYLA Engine (Spider-Man 2099 Asistente Holográfico Autónomo).
    Coordina memoria sólida híbrida, llamadas cloud a LLMs, síntesis/captura de audio y proactividad.
    """
    def __init__(self):
        self.config = Config()
        self.tracker = ResourceTracker(db_path=self.config.episodic_db_path)
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
        self.system = SystemTools(on_alarm_trigger=self.speak_reply)

    def _build_runtime_context(self) -> str:
        """Inyecta el estado real en vivo (modelo activo, tokens reales, sistema y agenda) en el prompt."""
        active_provider, active_model = self.router.get_active_model()
        stats = self.tracker.get_summary()
        avail = ", ".join(f"{o['provider']}:{o['model']}" for o in self.router.get_available_models())
        cal_ctx = self.calendar.get_prompt_context()
        sys_stat = self.system.get_system_status()
        return (
            "\n\n---\n\n"
            "### Estado en Tiempo Real del Sistema (Runtime Actual — Usa SIEMPRE estos datos reales si Víctor pregunta):\n"
            f"- Proveedor y Modelo LLM ACTIVO en este instante: **{active_provider} ({active_model})**\n"
            f"- Modelos disponibles para cambiar con `/model`: {avail}\n"
            f"- Tokens reales consumidos en esta sesión: {stats['total_tokens_in']} entrada / {stats['total_tokens_out']} salida ({stats['total_tokens']} totales)\n"
            f"- Llamadas reales por proveedor en esta sesión: {stats['calls_by_provider']}\n"
            f"- Tiempo de sesión activa: {stats['uptime_seconds']}s\n"
            f"- Telemetría Arch Linux de Víctor: CPU {sys_stat['cpu']} | RAM {sys_stat['ram']} | Disco {sys_stat['disk']} | Batería {sys_stat['battery']}\n\n"
            f"{cal_ctx}\n"
            "- Si Víctor te pide agendar/crear un evento en su calendario durante la conversación, incluye al final de tu respuesta la etiqueta exacta: "
            "`[CALENDAR_ADD: Título del evento | YYYY-MM-DD HH:MM]`.\n"
            "- Si Víctor te pide programar una alarma o temporizador (ej. 'pon una alarma en 5m para...'), incluye al final de tu respuesta la etiqueta exacta: "
            "`[ALARM_ADD: 5m | Mensaje de la alarma]`."
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
            advice_str = "\n\n  " + "\n  ".join(proactive_advice)
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
        """Limpia Markdown/iconos y reproduce la respuesta por voz si el audio está habilitado."""
        if self.config.audio_enabled:
            clean_speech = re.sub(r'[*_#`]', '', reply_text)
            self.tts.speak(clean_speech, play_audio=True)

    def _handle_calendar_tags(self, reply_text: str) -> str:
        """Detecta y ejecuta etiquetas [CALENDAR_ADD: ...] y [ALARM_ADD: ...] generadas por LYLA."""
        cal_pattern = r"\[CALENDAR_ADD:\s*([^|\]]+?)\s*\|\s*([^\]]+?)\s*\]"
        for title, dt_str in re.findall(cal_pattern, reply_text):
            ev = self.calendar.add_event(title=title.strip(), start_time=dt_str.strip())
            print(f"\n  [Calendario] Evento agendado: '{ev['title']}' → {ev['start_time']} ({ev['source']})")
        reply_text = re.sub(cal_pattern, "", reply_text)

        alarm_pattern = r"\[ALARM_ADD:\s*([^|\]]+?)\s*\|\s*([^\]]+?)\s*\]"
        for t_spec, msg in re.findall(alarm_pattern, reply_text):
            try:
                al = self.system.add_alarm(time_spec=t_spec.strip(), message=msg.strip())
                print(f"\n  [Alarma] Programada para las {al['target_time']}: '{al['message']}'")
            except Exception as e:
                print(f"\n  [Alarma] No se pudo programar: {e}")
        return re.sub(alarm_pattern, "", reply_text).strip()

    def get_models_status_report(self):
        """Devuelve el reporte de uso de tokens y porcentajes por modelo."""
        _, active_model = self.router.get_active_model()
        return self.tracker.get_models_status_report(
            self.router.get_available_models(),
            active_model=active_model
        )

    def format_models_status_text(self) -> str:
        """Devuelve un texto formateado con los tokens y porcentajes de cada modelo (para HUD/CLI)."""
        stats = self.tracker.get_summary()
        report = self.get_models_status_report()
        lines = ["󰐷  STATUS DE MODELOS CLOUD (TOKENS & PORCENTAJES HOY):"]
        for item in report:
            mark = "● [ACTIVO]" if item["active"] else "○"
            lines.append(
                f" {mark} {item['provider'].upper()} → {item['model']}\n"
                f"    Tokens hoy: {item['tokens_total']:,} / {item['daily_limit']:,} "
                f"({item['used_pct']:.2f}% usado | {item['remaining_pct']:.2f}% libre) • "
                f"Llamadas: {item['calls']} • Lat: {item['last_latency']:.2f}s"
            )
        lines.append(
            f"\n  Sesión actual: {stats['total_tokens_in']} in / {stats['total_tokens_out']} out "
            f"({stats['total_tokens']} total) • Uptime: {stats['uptime_seconds']}s"
        )
        return "\n".join(lines)

    def handle_hud_input(self, user_input: str, voice_enabled: bool = True) -> dict:
        """
        Procesa cualquier entrada desde la barra de texto del HUD.
        Soporta exactamente los mismos comandos del CLI (/model, /status, /comands, /calendar, /alarm, /memory, /sys, /voice, etc.)
        y mensajes conversacionales normales.
        """
        user_input = user_input.strip()
        if not user_input:
            return {"text": "", "speak": False, "voice_enabled": voice_enabled}

        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lower()
        cmd_arg = parts[1].strip() if len(parts) > 1 else None

        if cmd in ["/comands", "/commands", "/comandos", "/help", "/ayuda", "comands", "commands", "comandos", "help"]:
            txt = (
                "  COMANDOS DISPONIBLES EN LYLA (HUD & CLI):\n"
                " • /comands                  : Muestra esta lista de comandos\n"
                " • /model | /modelo [opción] : Rota al siguiente modelo o elige uno (/model groq, /model 1)\n"
                " • /status | /stats          : Muestra tokens y % de cuota de cada modelo\n"
                " • /calendar | /agenda       : Ver/agregar eventos (/calendar add Junta | 2026-11-08 16:00)\n"
                " • /alarm | /alarma <t> <m>  : Programa alarma (/alarm 5m Revisar deploy)\n"
                " • /sys | /system            : Telemetría Arch Linux (CPU, RAM, Disco, Batería)\n"
                " • /mobile [mensaje]         : Ping al teléfono vía KDE Connect\n"
                " • /memory                   : Ver recuerdos guardados en SQLite\n"
                " • /voice                    : Activa/desactiva respuestas por voz\n"
                " • /stop | /shh              : Silencia la voz de LYLA inmediatamente"
            )
            return {"text": txt, "speak": False, "voice_enabled": voice_enabled}

        if cmd in ["/stop", "/shh", "/calla", "stop", "shh"]:
            self.tts.player.stop()
            return {"text": "  Voz de LYLA silenciada.", "speak": False, "voice_enabled": voice_enabled}

        if cmd == "/voice":
            voice_enabled = not voice_enabled
            state_str = "ACTIVADA " if voice_enabled else "DESACTIVADA "
            if not voice_enabled:
                self.tts.player.stop()
            return {"text": f"Voz de LYLA: {state_str}", "speak": False, "voice_enabled": voice_enabled}

        if cmd in ["/status", "/stats", "status", "stats"]:
            return {"text": self.format_models_status_text(), "speak": False, "voice_enabled": voice_enabled}

        if cmd in ["/model", "/modelo", "model", "modelo"]:
            try:
                new_prov, new_mod = self.router.switch_model(cmd_arg)
                header = f"  Modelo cambiado a: {new_prov} ({new_mod})\n\n"
            except ValueError as err:
                header = f"  {err}\n\n"
            active_prov, active_mod = self.router.get_active_model()
            lines = [header + "󰯊  Modelos Disponibles:"]
            for idx, opt in enumerate(self.router.get_available_models(), start=1):
                is_act = (opt["provider"] == active_prov and opt["model"] == active_mod)
                mark = "●" if is_act else " "
                tag = " (ACTIVO)" if is_act else ""
                lines.append(f"  {mark} [{idx}] {opt['provider']} → {opt['model']}{tag}")
            return {"text": "\n".join(lines), "speak": False, "voice_enabled": voice_enabled}

        if cmd == "/memory":
            memories = self.memory.episodic.get_recent_memories(limit=8)
            if not memories:
                return {"text": "󰍛  Sin recuerdos en SQLite aún. Dile: 'Recuerda que...'", "speak": False, "voice_enabled": voice_enabled}
            lines = ["󰍛  Recuerdos en Memoria Episódica (SQLite):"]
            for m in memories:
                lines.append(f" • [{m['created_at'][:16]}] [{m['category'].upper()}] {m['summary']}")
            return {"text": "\n".join(lines), "speak": False, "voice_enabled": voice_enabled}

        if cmd in ["/calendar", "/agenda", "calendar", "agenda"]:
            if not cmd_arg:
                events = self.calendar.list_upcoming_events(limit=8)
                lines = [f"  Próximos Eventos ({self.calendar.get_status_label()}):"]
                if not events:
                    lines.append(" • (Sin eventos próximos. Usa '/calendar add Título | YYYY-MM-DD HH:MM')")
                else:
                    for ev in events:
                        lines.append(f" • [{ev['start_time']}] {ev['title']} (ID: {ev['id']}, {ev['source']})")
                return {"text": "\n".join(lines), "speak": False, "voice_enabled": voice_enabled}
            elif cmd_arg.lower().startswith("add "):
                raw_ev = cmd_arg[4:].strip()
                title_p, time_p = raw_ev.split("|", 1) if "|" in raw_ev else (raw_ev, "Hoy")
                ev = self.calendar.add_event(title_p.strip(), time_p.strip())
                return {"text": f"  Evento agendado: '{ev['title']}' → {ev['start_time']} ({ev['source']})", "speak": False, "voice_enabled": voice_enabled}
            elif cmd_arg.lower().startswith(("del ", "delete ", "rm ")):
                ev_id = cmd_arg.split(maxsplit=1)[1].strip()
                ok = self.calendar.delete_event(ev_id)
                return {"text": f"  Evento #{ev_id} eliminado." if ok else f"  No se encontró evento #{ev_id}.", "speak": False, "voice_enabled": voice_enabled}

        if cmd in ["/alarm", "/alarma", "alarm", "alarma"]:
            if not cmd_arg:
                alarms = self.system.list_active_alarms()
                if not alarms:
                    return {"text": "  Sin alarmas activas. Usa '/alarm 5m Revisar deploy' o '/alarm 18:30 Junta'", "speak": False, "voice_enabled": voice_enabled}
                lines = ["  Alarmas Activas:"]
                for al in alarms:
                    lines.append(f" • [#{al['id']}] {al['target_time']} → {al['message']}")
                return {"text": "\n".join(lines), "speak": False, "voice_enabled": voice_enabled}
            else:
                p_al = cmd_arg.split(maxsplit=1)
                t_spec = p_al[0]
                msg_al = p_al[1] if len(p_al) > 1 else "Alarma LYLA 2099"
                try:
                    al = self.system.add_alarm(t_spec, msg_al)
                    return {"text": f"  Alarma #{al['id']} programada para las {al['target_time']}: '{al['message']}'", "speak": False, "voice_enabled": voice_enabled}
                except ValueError as err:
                    return {"text": f"  {err}", "speak": False, "voice_enabled": voice_enabled}

        if cmd in ["/sys", "/system", "sys", "system"]:
            st = self.system.get_system_status()
            txt = (
                "󰣇  TELEMETRÍA ARCH LINUX (2099):\n"
                f" •   CPU      : {st['cpu']}\n"
                f" • 󰍛  Memoria  : {st['ram']}\n"
                f" • 󰋊  Matriz   : {st['disk']}\n"
                f" •   Batería  : {st['battery']}\n"
                f" •   En línea : {st['uptime']}"
            )
            return {"text": txt, "speak": False, "voice_enabled": voice_enabled}

        if cmd in ["/mobile", "mobile"]:
            res_mob = self.system.ping_mobile(cmd_arg or "Ping desde LYLA 2099 HUD")
            return {"text": f"  {res_mob}", "speak": False, "voice_enabled": voice_enabled}

        # Mensaje normal de conversación con LYLA
        reply = self.process_message(user_input, voice_reply=False)
        prov, mod = self.router.get_active_model()
        return {
            "text": f"LYLA [{prov}:{mod}] > {reply}",
            "raw_reply": reply,
            "speak": voice_enabled,
            "voice_enabled": voice_enabled,
        }

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
            print(f"\n󰍛  [Memoria Sólida] Se ha guardado en SQLite: '{fact}'")

    def remember(self, category: str, summary: str, details: str = "", tags: str = "", importance: int = 1):
        """Método explícito para almacenar un hecho en la memoria episódica."""
        return self.memory.consolidate_memory(category, summary, details, tags, importance)
