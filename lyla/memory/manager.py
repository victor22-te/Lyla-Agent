from pathlib import Path
from typing import List, Dict, Any
from .declarative import DeclarativeMemory
from .episodic import EpisodicMemory
from .session import SessionMemory

class MemoryManager:
    """
    Coordinador de Memoria Sólida Híbrida:
    - Capa 1: Declarativa (Markdown - reglas y perfil)
    - Capa 2: Episódica (SQLite - recuerdos a largo plazo)
    - Capa 3: Sesión (Buffer en RAM - conversación activa)
    """
    def __init__(self, config_dir: Path, db_path: Path, max_turns: int = 20):
        self.declarative = DeclarativeMemory(config_dir)
        self.episodic = EpisodicMemory(db_path)
        self.session = SessionMemory(max_turns)

    def build_system_prompt(self, user_query: str = "") -> str:
        """
        Construye el System Prompt completo inyectando:
        1. Reglas y personalidad de LYLA (Markdown)
        2. Perfil de Víctor (Markdown)
        3. Recuerdos episódicos relevantes (SQLite RAG ligero)
        """
        base_prompt = self.declarative.get_system_prompt_context()

        # Buscar recuerdos relevantes según la consulta
        relevant_memories = []
        if user_query:
            relevant_memories = self.episodic.search_memories(user_query, limit=3)
        else:
            relevant_memories = self.episodic.get_recent_memories(limit=3)

        memory_section = ""
        if relevant_memories:
            memory_lines = []
            for m in relevant_memories:
                date = m.get("created_at", "")[:10]
                summary = m.get("summary", "")
                cat = m.get("category", "")
                memory_lines.append(f"- [{date}] ({cat.upper()}): {summary}")
            memory_section = "\n\n### Recuerdos Relevantes en Memoria Episódica:\n" + "\n".join(memory_lines)

        return f"{base_prompt}{memory_section}"

    def record_interaction(self, user_text: str, assistant_text: str):
        self.session.add_turn("user", user_text)
        self.session.add_turn("assistant", assistant_text)

    def consolidate_memory(self, category: str, summary: str, details: str = "", tags: str = "", importance: int = 1):
        """Guarda un recuerdo duradero en la Capa 2 (SQLite)"""
        return self.episodic.add_memory(category, summary, details, tags, importance)
