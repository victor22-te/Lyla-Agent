import asyncio
from pathlib import Path
import edge_tts
from .player import AudioPlayer

class CloudTTS:
    """
    Sintetizador de Voz en la Nube (Edge-TTS).
    Zero Hardware Impact: Ejecuta la síntesis en servidores de Microsoft/Cloud de forma gratuita
    y reproduce el audio con tono natural en español.
    """
    def __init__(self, voice: str = "es-MX-DaliaNeural", output_dir: Path = None):
        self.voice = voice
        self.output_dir = output_dir or Path("/tmp")
        self.player = AudioPlayer()

    async def _generate_audio(self, text: str, output_path: Path):
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(str(output_path))

    def speak(self, text: str, play_audio: bool = True) -> Path:
        output_file = self.output_dir / "lyla_response.mp3"
        try:
            asyncio.run(self._generate_audio(text, output_file))
            if play_audio:
                self.player.play(output_file)
            return output_file
        except KeyboardInterrupt:
            self.player.stop()
            print("\r\033[K\033[93m  [Voz silenciada]\033[0m\n")
            return None
        except Exception as e:
            print(f"[CloudTTS] Error generando voz: {e}")
            return None
