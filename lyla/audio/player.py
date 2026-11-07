import os
import sys
import time
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
    permitiendo interrumpir la voz al instante con Espacio, Enter, q, Esc o Ctrl+C en CLI,
    o con el botón/atajo de Callar en las interfaces HUD/UI.
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
        proc = self.current_process
        self.current_process = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=0.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def play(self, audio_path: Path, interactive_cli: bool = True):
        if not self.player_cmd:
            print(f"[AudioPlayer] No se encontró reproductor de audio (mpv o pw-play). Archivo: {audio_path}")
            return

        if not audio_path or not Path(audio_path).exists():
            return

        # Detener cualquier audio previo antes de iniciar uno nuevo
        self.stop()

        cmd = self.player_cmd + [str(audio_path)]
        old_settings = None
        fd = None
        interrupted = False

        env = os.environ.copy()
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )

            use_tty_keys = (
                interactive_cli
                and sys.stdin is not None
                and sys.stdin.isatty()
                and termios is not None
                and tty is not None
            )
            if use_tty_keys:
                try:
                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    tty.setcbreak(fd)
                    sys.stdout.write(
                        "\r\033[93m  LYLA hablando... (Presiona [Espacio], [Enter], [q], [Esc] o [Ctrl+C] para silenciar)\033[0m"
                    )
                    sys.stdout.flush()
                except Exception:
                    use_tty_keys = False

            while self.current_process and self.current_process.poll() is None:
                if use_tty_keys:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if ready:
                        ch = sys.stdin.read(1)
                        if ch in (" ", "\n", "\r", "q", "Q", "\x1b", "\x03"):
                            interrupted = True
                            self.stop()
                            break
                else:
                    time.sleep(0.05)

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
            if use_tty_keys:
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                if interrupted:
                    print("\033[93m  [Voz silenciada]\033[0m\n")
