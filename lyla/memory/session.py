from typing import List, Dict, Any

class SessionMemory:
    """
    Capa 3: Memoria de Trabajo y Sesión en Memoria (Buffer In-Memory).
    Mantiene el flujo de la conversación activa y permite sintetizar al finalizar.
    """
    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self.history: List[Dict[str, str]] = [] # [{'role': 'user'|'assistant', 'content': '...'}]

    def add_turn(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_turns * 2:
            # Mantener un límite para no inflar tokens de contexto
            self.history = self.history[-self.max_turns * 2:]

    def get_history(self) -> List[Dict[str, str]]:
        return list(self.history)

    def clear(self):
        self.history.clear()
