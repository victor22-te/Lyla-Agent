import subprocess
import shutil
from pathlib import Path

class AudioPlayer:
    """
    Reproductor de audio ligero para Arch Linux / PipeWire.
    Utiliza pw-play o mpv sin interfaz gráfica para no consumir recursos.
    """
    def __init__(self):
        self.player_cmd = None
        if shutil.which("mpv"):
            self.player_cmd = ["mpv", "--no-video", "--really-quiet"]
        elif shutil.which("pw-play"):
            self.player_cmd = ["pw-play"]
        elif shutil.which("paplay"):
            self.player_cmd = ["paplay"]

    def play(self, audio_path: Path):
        if not self.player_cmd:
            print(f"[AudioPlayer] No se encontró reproductor de audio (mpv o pw-play). Archivo: {audio_path}")
            return
        try:
            cmd = self.player_cmd + [str(audio_path)]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[AudioPlayer] Error al reproducir audio: {e}")
