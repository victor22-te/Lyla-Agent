from pathlib import Path
from ..core.config import Config

class CloudSTT:
    """
    Transcriptor de Audio en la Nube (Cloud STT).
    Soporta Groq Whisper API (ultra-rápido y gratuito) o Gemini Audio.
    Zero Hardware Impact: Ningún modelo corre en local.
    """
    def __init__(self, config: Config):
        self.config = config

    def transcribe(self, audio_file: Path) -> str:
        if not audio_file.exists():
            return ""

        # Prioridad 1: Groq Whisper Cloud
        if self.config.groq_api_key:
            try:
                from groq import Groq
                client = Groq(api_key=self.config.groq_api_key)
                with open(audio_file, "rb") as file:
                    transcription = client.audio.transcriptions.create(
                        file=(audio_file.name, file.read()),
                        model="whisper-large-v3",
                        language="es",
                        response_format="text"
                    )
                return str(transcription).strip()
            except Exception as e:
                print(f"[CloudSTT] Falló Groq Whisper ({e}), intentando fallback...")

        # Prioridad 2: Gemini Audio
        if self.config.gemini_api_key:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=self.config.gemini_api_key)
                with open(audio_file, "rb") as f:
                    audio_bytes = f.read()
                response = client.models.generate_content(
                    model=self.config.gemini_model,
                    contents=[
                        types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                        "Transcribe con exactitud el audio en español. Devuelve únicamente el texto transcrito sin comentarios."
                    ]
                )
                return response.text.strip() if response.text else ""
            except Exception as e:
                print(f"[CloudSTT] Error transcribiendo con Gemini: {e}")

        return ""
