import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

# Cargar variables de .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"

def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

class Config:
    def __init__(self):
        self.raw = load_settings()
        self.base_dir = BASE_DIR
        self.config_dir = CONFIG_DIR
        
        # Keys
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        
        # Agent config
        agent_cfg = self.raw.get("agent", {})
        self.agent_name = agent_cfg.get("name", "LYLA")
        self.language = agent_cfg.get("language", "es")
        
        # LLM config
        llm_cfg = self.raw.get("llm", {})
        self.default_provider = llm_cfg.get("default_provider", "gemini")
        self.gemini_model = llm_cfg.get("gemini", {}).get("model", "gemini-2.5-flash")
        self.groq_model = llm_cfg.get("groq", {}).get("model", "llama-3.3-70b-versatile")
        
        # Audio config
        audio_cfg = self.raw.get("audio", {})
        self.audio_enabled = audio_cfg.get("enabled", True)
        self.stt_provider = audio_cfg.get("stt_provider", "groq")
        self.tts_provider = audio_cfg.get("tts_provider", "edge-tts")
        self.tts_voice = audio_cfg.get("voice", "es-MX-DaliaNeural")
        self.temp_audio_dir = BASE_DIR / audio_cfg.get("temp_audio_dir", "temp_audio")
        self.temp_audio_dir.mkdir(parents=True, exist_ok=True)
        
        # Memory config
        mem_cfg = self.raw.get("memory", {})
        self.declarative_path = BASE_DIR / mem_cfg.get("declarative_path", "config")
        self.episodic_db_path = BASE_DIR / mem_cfg.get("episodic_db_path", "lyla_memory.db")
        self.max_session_history = mem_cfg.get("max_session_history", 20)
