import sys
import select
import subprocess
import shutil
from pathlib import Path
from typing import Optional

try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None


class AudioPlayer:
    """
    Reproductor de audio ligero para Arch Linux / PipeWire.
    Utiliza pw-play o mpv sin interfaz gráfica para no consumir recursos,
    permitiendo interrumpir la voz al instante con Espacio, Enter, q, Esc o Ctrl+C.
    """
    def __init__(self):
        self.player_cmd = None
        self.current_process: Optional[subprocess.Popen] = None
        if shutil.which("mpv"):
            self.player_cmd = ["mpv", "--no-video", "--no-terminal", "--really-quiet"]
        elif shutil.which("pw-play"):
            self.player_cmd = ["pw-play"]
        elif shutil.which("paplay"):
            self.player_cmd = ["paplay"]

    def stop(self):
        """Detiene inmediatamente cualquier reproducción de audio en curso."""
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=0.5)
            except Exception:
                try:
                    self.current_process.kill()
                except Exception:
                    pass
        self.current_process = None

    def play(self, audio_path: Path):
        if not self.player_cmd:
            print(f"[AudioPlayer] No se encontró reproductor de audio (mpv o pw-play). Archivo: {audio_path}")
            return

        cmd = self.player_cmd + [str(audio_path)]
        old_settings = None
        fd = None
        interrupted = False

        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            is_tty = sys.stdin.isatty() and termios is not None and tty is not None
            if is_tty:
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                tty.setcbreak(fd)

            sys.stdout.write(
                "\r\033[93m🔊 LYLA hablando... (Presiona [Espacio], [Enter], [q], [Esc] o [Ctrl+C] para silenciar)\033[0m"
            )
            sys.stdout.flush()

            while self.current_process and self.current_process.poll() is None:
                if is_tty:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if ready:
                        ch = sys.stdin.read(1)
                        if ch in (" ", "\n", "\r", "q", "Q", "\x1b", "\x03"):
                            interrupted = True
                            self.stop()
                            break
                else:
                    self.current_process.wait(timeout=0.05)

        except KeyboardInterrupt:
            interrupted = True
            self.stop()
        except Exception as e:
            self.stop()
            print(f"\n[AudioPlayer] Error al reproducir audio: {e}")
        finally:
            if old_settings is not None and fd is not None:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass
            # Limpiar la línea de estado temporal
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            if interrupted:
                print("\033[93m🔇 [Voz silenciada]\033[0m\n")
