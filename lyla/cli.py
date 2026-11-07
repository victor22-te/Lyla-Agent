import sys
import argparse
from pathlib import Path
from .core.agent import LylaAgent

CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

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
    voice_enabled = args.voice or agent.config.audio_enabled

    print(BANNER)
    print(f"{GREEN}● Sistema en línea.{RESET} Proveedor por defecto: {YELLOW}{agent.config.default_provider}{RESET}")
    print(f"Comandos rápidos: {BOLD}/voice{RESET} (activar/desactivar voz), {BOLD}/listen{RESET} (hablar por micrófono), {BOLD}/memory{RESET} (ver recuerdos), {BOLD}/stats{RESET} (ver tokens), {BOLD}/exit{RESET}\n")

    # Verificar si hay claves de API configuradas
    if not agent.config.gemini_api_key and not agent.config.groq_api_key:
        print(f"{YELLOW}⚠️  Aviso: No se han detectado GEMINI_API_KEY o GROQ_API_KEY en el entorno o archivo .env.{RESET}")
        print(f"   Puedes copiar {BOLD}.env.example{RESET} a {BOLD}.env{RESET} y añadir tus claves para interactuar con la nube.\n")

    while True:
        try:
            prompt_symbol = f"{CYAN}Víctor > {RESET}"
            user_input = input(prompt_symbol).strip()
            
            if not user_input:
                continue

            # Comandos internos
            if user_input.lower() in ["/exit", "exit", "salir", "quit"]:
                print(f"\n{MAGENTA}LYLA: Hasta la próxima, Víctor. Guardando estado y memoria...{RESET}")
                break

            elif user_input.lower() == "/voice":
                voice_enabled = not voice_enabled
                status = f"{GREEN}ACTIVADA{RESET}" if voice_enabled else f"{YELLOW}DESACTIVADA{RESET}"
                print(f"🔊 Voz de LYLA: {status}\n")
                continue

            elif user_input.lower() == "/stats":
                stats = agent.tracker.get_summary()
                print(f"\n{YELLOW}📊 Estadísticas de Recursos Cloud:{RESET}")
                print(f"  - Tokens entrada : {stats['total_tokens_in']}")
                print(f"  - Tokens salida  : {stats['total_tokens_out']}")
                print(f"  - Total tokens   : {stats['total_tokens']}")
                print(f"  - Llamadas APIs  : {stats['calls_by_provider']}")
                print(f"  - Tiempo sesión  : {stats['uptime_seconds']}s\n")
                continue

            elif user_input.lower() == "/memory":
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

            elif user_input.lower() == "/listen":
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

            # Procesamiento de mensaje normal
            reply = agent.process_message(user_input, voice_reply=voice_enabled)
            print(f"\n{MAGENTA}LYLA > {RESET}{reply}\n")

        except KeyboardInterrupt:
            print(f"\n\n{MAGENTA}LYLA: Interrupción detectada. Hasta luego, Víctor.{RESET}")
            break
        except Exception as e:
            print(f"\n{YELLOW}[Error]: {e}{RESET}\n")

if __name__ == "__main__":
    main()
