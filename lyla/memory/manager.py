import json
import re
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional
from .declarative import DeclarativeMemory
from .episodic import EpisodicMemory
from .session import SessionMemory

# Cada cuántos turnos de conversación se intenta la consolidación automática.
CONSOLIDATION_EVERY_TURNS = 10

ALLOWED_CATEGORIES = {"fact", "preference", "decision", "project", "conversation"}

EXTRACTION_SYSTEM_PROMPT = """Eres el consolidador de memoria de LYLA, una asistente de IA.
Tu trabajo es leer una conversación reciente y extraer SOLO los hechos duraderos
que vale la pena recordar a largo plazo: preferencias del usuario, decisiones,
datos personales o de sus proyectos, y compromisos.

Reglas:
- Solo guarda hechos duraderos. NO guardes saludos, preguntas puntuales, errores
  de tipeo, ni cosas que ya se resolvieron en la misma conversación.
- Sé conservador: si no hay nada que valga la pena, devuelve una lista vacía.
- Resume cada hecho en una frase corta y clara (summary), con contexto en details.
- category debe ser una de: fact, preference, decision, project, conversation.
- importance: 1-2 trivial, 3 normal, 4 importante, 5 crítico (cumpleaños, contraseñas NO — nunca guardes contraseñas ni códigos).
- tags: palabras clave separadas por comas, en minúsculas.

Devuelve ÚNICAMENTE un JSON válido con esta forma, sin texto extra ni bloques de código:
[{"category": "preference", "summary": "Víctor prefiere el té al café", "details": "Lo dijo al hablar de su desayuno", "tags": "bebida,desayuno", "importance": 3}]
Si no hay nada que guardar: []"""


def _parse_extraction(reply: str) -> List[Dict[str, Any]]:
    """Extrae la lista de recuerdos del JSON que devuelve el LLM. [] si no hay nada válido."""
    if not reply:
        return []
    text = reply.strip()
    # Quitar fences ```json ... ``` si los hay.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except Exception:
        # Intentar rescatar el primer [...] del texto.
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "fact")).strip().lower()
        summary = str(item.get("summary", "")).strip()
        if category not in ALLOWED_CATEGORIES or not summary:
            continue
        try:
            importance = int(item.get("importance", 2))
        except Exception:
            importance = 2
        out.append({
            "category": category,
            "summary": summary,
            "details": str(item.get("details", "")).strip(),
            "tags": str(item.get("tags", "")).strip().lower(),
            "importance": max(1, min(5, importance)),
        })
    return out


class MemoryManager:
    """
    Coordinador de Memoria Sólida Híbrida:
    - Capa 1: Declarativa (Markdown - reglas y perfil)
    - Capa 2: Episódica (SQLite - recuerdos a largo plazo, búsqueda híbrida)
    - Capa 3: Sesión (Buffer en RAM - conversación activa)

    La consolidación automática extrae hechos duraderos de la conversación
    con el LLM cada N turnos (en segundo plano) y los guarda en la Capa 2,
    además de los guardados explícitos ("recuerda que...").
    """
    def __init__(self, config_dir: Path, db_path: Path, max_turns: int = 20, embedder=None):
        self.declarative = DeclarativeMemory(config_dir)
        self.episodic = EpisodicMemory(db_path, embedder=embedder)
        self.session = SessionMemory(max_turns)
        self._turns_since_consolidation = 0

    def build_system_prompt(self, user_query: str = "") -> str:
        """
        Construye el System Prompt completo inyectando:
        1. Reglas y personalidad de LYLA (Markdown)
        2. Perfil de Víctor (Markdown)
        3. Recuerdos episódicos relevantes (SQLite, búsqueda híbrida keyword + semántica)
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
        self._turns_since_consolidation += 1

    def needs_consolidation(self, threshold: int = CONSOLIDATION_EVERY_TURNS) -> bool:
        """True cuando ya pasaron suficientes turnos desde la última consolidación."""
        return self._turns_since_consolidation >= threshold

    def consolidate_session(self, generate_fn: Callable[[str, str], str], max_turns: int = 10) -> int:
        """
        Extrae hechos duraderos de la conversación reciente con el LLM y los
        guarda en la Capa 2. generate_fn(system_prompt, transcript) -> texto JSON.
        Devuelve cuántos recuerdos nuevos se guardaron. No duplica lo ya guardado.
        """
        history = self.session.get_history()[-max_turns * 2:]
        if len(history) < 4:
            self._turns_since_consolidation = 0
            return 0
        transcript = "\n".join(f"{t['role']}: {t['content']}" for t in history)
        try:
            reply = generate_fn(EXTRACTION_SYSTEM_PROMPT, transcript)
        except Exception as e:
            print(f"[Memoria] Extracción falló: {e}")
            return 0
        memories = _parse_extraction(reply)
        saved = 0
        for m in memories:
            try:
                if self.episodic.find_similar(m["summary"], m.get("details", "")):
                    continue
                self.episodic.add_memory(
                    category=m["category"],
                    summary=m["summary"],
                    details=m.get("details", ""),
                    tags=m.get("tags", ""),
                    importance=m.get("importance", 2),
                )
                saved += 1
            except Exception as e:
                print(f"[Memoria] No se pudo guardar '{m.get('summary', '')}': {e}")
        self._turns_since_consolidation = 0
        if saved:
            print(f"[Memoria] Consolidación automática: {saved} recuerdo(s) nuevo(s) guardado(s).")
        return saved

    def consolidate_memory(self, category: str, summary: str, details: str = "", tags: str = "", importance: int = 1):
        """Guarda un recuerdo duradero en la Capa 2 (SQLite). No duplica lo ya guardado."""
        existing = self.episodic.find_similar(summary, details)
        if existing is not None:
            print(f"[Memoria] Ya existe un recuerdo parecido (#{existing['id']}), no se duplica.")
            return existing["id"]
        return self.episodic.add_memory(category, summary, details, tags, importance)
