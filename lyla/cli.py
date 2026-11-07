import sys
import argparse
from pathlib import Path
from typing import List, Optional
from .core.agent import LylaAgent

try:
    import readline
except ImportError:
    readline = None

CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
PURE_RED = "\033[38;2;255;0;0m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Envolver códigos ANSI con \001 y \002 para que readline calcule bien el cursor al usar Tab/flechas
RL_CYAN = f"\001{CYAN}\002"
RL_RESET = f"\001{RESET}\002"

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ASCII_ART_PATH = ASSETS_DIR / "ascii.txt"

CLI_COMMANDS = [
    "/comands",
    "/commands",
    "/comandos",
    "/calendar",
    "/agenda",
    "/voice",
    "/listen",
    "/memory",
    "/model",
    "/modelo",
    "/stats",
    "/help",
    "/exit",
]

BARE_COMMANDS = [
    "comands",
    "commands",
    "comandos",
    "calendar",
    "agenda",
    "model",
    "modelo",
    "exit",
    "salir",
    "quit",
]


def setup_autocomplete(agent: LylaAgent):
    """Configura autocompletado con Tab en la terminal para comandos y modelos."""
    if readline is None:
        return

    def completer(text: str, state: int) -> Optional[str]:
        line = readline.get_line_buffer()
        stripped = line.lstrip()
        tokens = stripped.split()

        # Si el usuario está escribiendo argumentos para /model o /modelo
        if stripped and (
            stripped.startswith(("/model ", "/modelo ", "model ", "modelo "))
        ):
            options_models = agent.router.get_available_models()
            candidates: List[str] = ["gemini", "groq"]
            for idx, opt in enumerate(options_models, start=1):
                if opt["model"] not in candidates:
                    candidates.append(opt["model"])
                candidates.append(str(idx))
            matches = [c for c in candidates if c.lower().startswith(text.lower())]
        elif not tokens or (len(tokens) == 1 and not line.endswith(" ")):
            # Autocompletar comandos principales
            if text.startswith("/") or not text:
                pool = CLI_COMMANDS
            else:
                pool = CLI_COMMANDS + BARE_COMMANDS
            matches = [cmd + " " if cmd in ("/model", "/modelo") and cmd == text else cmd
                       for cmd in pool if cmd.lower().startswith(text.lower())]
        else:
            matches = []

        return matches[state] if state < len(matches) else None

    # No separar por '/' ni '-' para que /comando y nombres de modelos autocompleten enteros
    readline.set_completer_delims(" \t\n")
    readline.set_completer(completer)
    if getattr(readline, "__doc__", "") and "libedit" in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set show-all-if-ambiguous on")


def print_models_status(agent: LylaAgent):
    """Muestra la lista de modelos disponibles marcando el activo."""
    active_provider, active_model = agent.router.get_active_model()
    options = agent.router.get_available_models()
    print(f"\n{CYAN}{BOLD}🤖 Modelos / Proveedores Disponibles:{RESET}")
    for idx, opt in enumerate(options, start=1):
        is_active = (opt["provider"] == active_provider and opt["model"] == active_model)
        marker = f"{GREEN}●{RESET}" if is_active else " "
        active_tag = f" {GREEN}(ACTIVO){RESET}" if is_active else ""
        print(f"  {marker} [{idx}] {YELLOW}{opt['provider']}{RESET} → {BOLD}{opt['model']}{RESET}{active_tag}")
    print(f"  {CYAN}Tip:{RESET} Escribe {BOLD}/model{RESET} (o {BOLD}/modelo{RESET}) de nuevo para rotar al siguiente, o {BOLD}/model <número|proveedor|modelo>{RESET}.\n")


def load_ascii_art() -> str:
    """Carga el arte ASCII de Spider-Man 2099 / LYLA desde lyla/assets/ascii.txt en rojo puro."""
    if ASCII_ART_PATH.exists():
        art = ASCII_ART_PATH.read_text(encoding="utf-8").rstrip()
        return f"\n{PURE_RED}{BOLD}{art}{RESET}"
    return ""


def print_commands_list():
    """Muestra todos los comandos disponibles registrados en SKILLS.md."""
    print(
        f"\n{CYAN}{BOLD}📋 Comandos Disponibles en LYLA (SKILLS.md):{RESET}\n"
        f"  {BOLD}/comands{RESET}                  : Muestra esta lista de comandos disponibles\n"
        f"  {BOLD}/model{RESET} | {BOLD}/modelo{RESET} [opción] : Cambia al siguiente modelo disponible o selecciona uno específico\n"
        f"  {BOLD}/calendar{RESET} | {BOLD}/agenda{RESET}       : Muestra próximos eventos, agrega ('/calendar add Título | YYYY-MM-DD HH:MM') o vincula Google ('/calendar auth')\n"
        f"  {BOLD}/voice{RESET}                    : Activa o desactiva la síntesis de voz (Edge-TTS)\n"
        f"  {BOLD}/listen{RESET}                   : Graba tu voz con micrófono y la transcribe en la nube\n"
        f"  {BOLD}/memory{RESET}                   : Muestra los recuerdos guardados en Memoria Episódica (SQLite)\n"
        f"  {BOLD}/stats{RESET}                    : Muestra consumo de tokens y llamadas a cada proveedor cloud\n"
        f"  {BOLD}/exit{RESET}                     : Cierra la sesión de LYLA\n"
        f"\n{CYAN}{BOLD}⌨️  Atajos durante la voz de LYLA:{RESET}\n"
        f"  {BOLD}[Espacio]{RESET}, {BOLD}[Enter]{RESET}, {BOLD}[q]{RESET}, {BOLD}[Esc]{RESET} o {BOLD}[Ctrl+C]{RESET} : Silencia la voz al instante y devuelve el prompt sin salir del CLI\n"
    )


BANNER = f"""
{CYAN}{BOLD}╔═══════════════════════════════════════════════════════════════╗
║   LYLA // Lightweight Yielding Lifeform Assembly (2099)       ║
║   Agente Autónomo Cloud-First • Zero Impact • Memoria Híbrida ║
╚═══════════════════════════════════════════════════════════════╝{RESET}
"""

def main():
    parser = argparse.ArgumentParser(description="LYLA AI Assistant (Spider-Man 2099)")
    parser.add_argument("--voice", action="store_true", help="Activar respuestas por voz por defecto")
    args = parser.parse_args()

    agent = LylaAgent()
    setup_autocomplete(agent)
    voice_enabled = args.voice or agent.config.audio_enabled
    active_provider, active_model = agent.router.get_active_model()

    ascii_art = load_ascii_art()
    if ascii_art:
        print(ascii_art)
    print(BANNER)
    print(
        f"{GREEN}● Sistema en línea.{RESET} Proveedor por defecto: "
        f"{YELLOW}{active_provider}{RESET} ({BOLD}{active_model}{RESET})"
    )
    print(
        f"Comandos rápidos (Tab para autocompletar): "
        f"{BOLD}/comands{RESET} (ver comandos), "
        f"{BOLD}/model{RESET} o {BOLD}/modelo{RESET} (cambiar modelo), "
        f"{BOLD}/voice{RESET} (activar/desactivar voz), "
        f"{BOLD}/listen{RESET} (hablar por micrófono), "
        f"{BOLD}/memory{RESET} (ver recuerdos), "
        f"{BOLD}/stats{RESET} (ver tokens), "
        f"{BOLD}/exit{RESET}\n"
    )

    # Verificar si hay claves de API configuradas
    if not agent.config.gemini_api_key and not agent.config.groq_api_key:
        print(f"{YELLOW}⚠️  Aviso: No se han detectado GEMINI_API_KEY o GROQ_API_KEY en el entorno o archivo .env.{RESET}")
        print(f"   Puedes copiar {BOLD}.env.example{RESET} a {BOLD}.env{RESET} y añadir tus claves para interactuar con la nube.\n")

    while True:
        try:
            prompt_symbol = f"{RL_CYAN}Víctor > {RL_RESET}"
            user_input = input(prompt_symbol).strip()
            
            if not user_input:
                continue

            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            cmd_arg = parts[1].strip() if len(parts) > 1 else None

            # Comandos internos
            if cmd in ["/exit", "exit", "salir", "quit"] and cmd_arg is None:
                print(f"\n{MAGENTA}LYLA: Hasta la próxima, Víctor. Guardando estado y memoria...{RESET}")
                break

            elif cmd in ["/comands", "/commands", "/comandos", "/help", "/ayuda", "comands", "commands", "comandos", "help"]:
                print_commands_list()
                continue

            elif cmd in ["/calendar", "/agenda", "calendar", "agenda"]:
                if not cmd_arg:
                    events = agent.calendar.list_upcoming_events(limit=10)
                    print(f"\n{CYAN}{BOLD}📅 Próximos Eventos ({agent.calendar.get_status_label()}):{RESET}")
                    if not events:
                        print("  (No hay eventos próximos. Usa '/calendar add Reunión | 2026-11-08 16:00' o díselo a LYLA en el chat)")
                    else:
                        for ev in events:
                            print(f"  - [{YELLOW}{ev['start_time']}{RESET}] {BOLD}{ev['title']}{RESET} (ID: {ev['id']}, {ev['source']})")
                    print(
                        f"  {CYAN}Comandos:{RESET} {BOLD}/calendar add <título> | <YYYY-MM-DD HH:MM>{RESET} • "
                        f"{BOLD}/calendar del <id>{RESET} • {BOLD}/calendar auth{RESET}\n"
                    )
                elif cmd_arg.lower() == "auth":
                    ok, msg = agent.calendar.authenticate_oauth()
                    color = GREEN if ok else YELLOW
                    print(f"\n{color}{msg}{RESET}\n")
                elif cmd_arg.lower().startswith("add "):
                    raw_ev = cmd_arg[4:].strip()
                    if "|" in raw_ev:
                        title_part, time_part = raw_ev.split("|", 1)
                    else:
                        title_part, time_part = raw_ev, "Hoy"
                    ev = agent.calendar.add_event(title_part.strip(), time_part.strip())
                    print(f"\n{GREEN}📅 Evento agendado:{RESET} '{BOLD}{ev['title']}{RESET}' → {YELLOW}{ev['start_time']}{RESET} ({ev['source']})\n")
                elif cmd_arg.lower().startswith(("del ", "delete ", "rm ")):
                    ev_id = cmd_arg.split(maxsplit=1)[1].strip()
                    if agent.calendar.delete_event(ev_id):
                        print(f"\n{GREEN}🗑️  Evento #{ev_id} eliminado.{RESET}\n")
                    else:
                        print(f"\n{YELLOW}⚠️  No se encontró el evento local #{ev_id}.{RESET}\n")
                else:
                    print(f"\n{YELLOW}Uso: /calendar | /calendar add <título> | <fecha_hora> | /calendar del <id> | /calendar auth{RESET}\n")
                continue

            elif cmd in ["/model", "/modelo", "model", "modelo"]:
                try:
                    new_provider, new_model = agent.router.switch_model(cmd_arg)
                    print(
                        f"\n🔄 Modelo cambiado a: {YELLOW}{new_provider}{RESET} "
                        f"({BOLD}{new_model}{RESET})"
                    )
                    print_models_status(agent)
                except ValueError as err:
                    print(f"\n{YELLOW}⚠️  {err}{RESET}")
                    print_models_status(agent)
                continue

            elif cmd == "/voice":
                voice_enabled = not voice_enabled
                status = f"{GREEN}ACTIVADA{RESET}" if voice_enabled else f"{YELLOW}DESACTIVADA{RESET}"
                print(f"🔊 Voz de LYLA: {status}\n")
                continue

            elif cmd == "/stats":
                stats = agent.tracker.get_summary()
                print(f"\n{YELLOW}📊 Estadísticas de Recursos Cloud:{RESET}")
                print(f"  - Tokens entrada : {stats['total_tokens_in']}")
                print(f"  - Tokens salida  : {stats['total_tokens_out']}")
                print(f"  - Total tokens   : {stats['total_tokens']}")
                print(f"  - Llamadas APIs  : {stats['calls_by_provider']}")
                print(f"  - Tiempo sesión  : {stats['uptime_seconds']}s\n")
                continue

            elif cmd == "/memory":
                memories = agent.memory.episodic.get_recent_memories(limit=10)
                print(f"\n{MAGENTA}🧠 Recuerdos Registrados en Memoria Episódica (SQLite):{RESET}")
                if not memories:
                    print("  (Sin recuerdos almacenados aún. Dile: 'Recuerda que...')")
                else:
                    for m in memories:
                        date = m['created_at'][:16]
                        print(f"  [{date}] [{m['category'].upper()}] (Imp: {m['importance']}) {m['summary']}")
                print()
                continue

            elif cmd == "/listen":
                print(f"\n{CYAN}🎤 Grabando con PipeWire... Presiona [Enter] para detener y enviar a la nube.{RESET}")
                rec_file = agent.capture.start_recording()
                input()
                agent.capture.stop_recording()
                print(f"⏳ Transcribiendo audio en la nube...")
                transcription = agent.stt.transcribe(rec_file)
                if not transcription:
                    print(f"{YELLOW}No se detectó audio claro o faltan claves de STT.{RESET}\n")
                    continue
                print(f"{CYAN}Víctor (Voz) > {transcription}{RESET}")
                user_input = transcription

            # Procesamiento de mensaje normal (imprime texto primero y luego reproduce voz)
            reply = agent.process_message(user_input, voice_reply=False)
            cur_prov, cur_mod = agent.router.get_active_model()
            print(f"\n{MAGENTA}LYLA [{cur_prov}:{cur_mod}] > {RESET}{reply}\n")
            if voice_enabled:
                agent.speak_reply(reply)

        except KeyboardInterrupt:
            agent.tts.player.stop()
            print(f"\n{YELLOW}🔇 [Interrumpido] Puedes seguir escribiendo. (Usa /exit para cerrar LYLA){RESET}\n")
            continue
        except EOFError:
            agent.tts.player.stop()
            print(f"\n\n{MAGENTA}LYLA: Hasta luego, Víctor.{RESET}")
            break
        except Exception as e:
            print(f"\n{YELLOW}[Error]: {e}{RESET}\n")

if __name__ == "__main__":
    main()
