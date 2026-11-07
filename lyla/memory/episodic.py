import sqlite3
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

class EpisodicMemory:
    """
    Capa 2: Memoria Episódica en SQLite.
    Almacena hechos pasados, decisiones y notas de forma estructurada y ultraligera
    sin consumir memoria RAM constante ni requerir servidores externos.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    category TEXT NOT NULL, -- 'decision', 'fact', 'conversation', 'preference', 'project'
                    summary TEXT NOT NULL,
                    details TEXT,
                    tags TEXT, -- Separados por comas: 'linux,audio,gemini'
                    importance INTEGER DEFAULT 1 -- Escala de 1 a 5
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories(tags);
            """)
            conn.commit()

    def add_memory(self, category: str, summary: str, details: str = "", tags: str = "", importance: int = 1) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memories (category, summary, details, tags, importance)
                VALUES (?, ?, ?, ?, ?)
            """, (category, summary, details, tags.lower(), importance))
            conn.commit()
            return cursor.lastrowid

    def search_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Búsqueda rápida por palabras clave en resumen, detalles y etiquetas.
        """
        terms = [f"%{t.strip().lower()}%" for t in query.split() if len(t.strip()) > 2]
        if not terms:
            # Si no hay términos de búsqueda claros, devolver los más recientes de alta importancia
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, created_at, category, summary, details, tags, importance
                    FROM memories
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]

        # Búsqueda por coincidencia
        where_clauses = []
        params = []
        for term in terms:
            where_clauses.append("(LOWER(summary) LIKE ? OR LOWER(details) LIKE ? OR LOWER(tags) LIKE ?)")
            params.extend([term, term, term])

        sql = f"""
            SELECT id, created_at, category, summary, details, tags, importance
            FROM memories
            WHERE {" OR ".join(where_clauses)}
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
        """
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_recent_memories(self, limit: int = 5) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, created_at, category, summary, details, tags, importance
                FROM memories
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
