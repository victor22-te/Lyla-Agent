import sqlite3
import datetime
import struct
from pathlib import Path
from typing import List, Dict, Any, Optional

from .embeddings import cosine_similarity

# Umbral mínimo de similitud semántica para que un recuerdo entre en los resultados.
VECTOR_MIN_SCORE = 0.5
# Umbral para considerar que un recuerdo nuevo ya existe (deduplicación).
DEDUP_VECTOR_SCORE = 0.85


def _vector_to_blob(vec: List[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _blob_to_vector(blob: bytes) -> List[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob[: n * 4]))


def _normalize_terms(text: str) -> List[str]:
    """Términos normalizados (sin acentos, minúsculas) para comparar recuerdos."""
    import unicodedata
    import re
    no_accents = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return [t for t in re.findall(r"[a-z0-9]+", no_accents.lower()) if len(t) > 2]


class EpisodicMemory:
    """
    Capa 2: Memoria Episódica en SQLite.
    Almacena hechos pasados, decisiones y notas de forma estructurada y ultraligera
    sin consumir memoria RAM constante ni requerir servidores externos.

    Búsqueda híbrida: palabras clave (LIKE) + semántica (embeddings Gemini,
    similitud coseno). Si no hay embeddings, la búsqueda por palabras clave
    sigue funcionando igual que antes.
    """
    def __init__(self, db_path: Path, embedder=None):
        self.db_path = db_path
        self.embedder = embedder
        self._init_db()

    def set_embedder(self, embedder):
        self.embedder = embedder

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Esperar hasta 5s si otro hilo/proceso está escribiendo (la consolidación
        # automática corre en segundo plano).
        conn.execute("PRAGMA busy_timeout = 5000")
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
            # Migración: columna de embedding (vector float32 serializado).
            # Las bases viejas la obtienen sin perder sus recuerdos.
            cols = [r[1] for r in cursor.execute("PRAGMA table_info(memories)").fetchall()]
            if "embedding" not in cols:
                cursor.execute("ALTER TABLE memories ADD COLUMN embedding BLOB")
            conn.commit()

    def add_memory(self, category: str, summary: str, details: str = "", tags: str = "", importance: int = 1, embedder=None) -> int:
        emb = embedder if embedder is not None else self.embedder
        blob = None
        if emb is not None:
            vec = emb.embed(f"{summary}. {details}".strip(". "))
            if vec:
                blob = _vector_to_blob(vec)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memories (category, summary, details, tags, importance, embedding)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (category, summary, details, tags.lower(), importance, blob))
            conn.commit()
            return cursor.lastrowid

    def search_memories(self, query: str, limit: int = 5, embedder=None) -> List[Dict[str, Any]]:
        """
        Búsqueda híbrida:
        - Palabras clave en resumen, detalles y etiquetas (como antes).
        - Semántica: similitud coseno con los embeddings guardados (si hay embedder).
        Los resultados se mezclan por puntaje (coincidencia + importancia) y se
        devuelven los mejores. Sin embedder, es la búsqueda de antes.
        """
        emb = embedder if embedder is not None else self.embedder
        scored: Dict[int, Dict[str, Any]] = {}

        # 1. Palabras clave (SQL LIKE, igual que antes).
        keyword_rows = self._search_keyword(query, limit=limit * 2)
        for row in keyword_rows:
            row = dict(row)
            row["score"] = 1.0 + 0.1 * int(row.get("importance", 1))
            row["match"] = "keyword"
            scored[row["id"]] = row

        # 2. Búsqueda semántica por embeddings.
        if emb is not None and query and query.strip():
            query_vec = emb.embed(query)
            if query_vec:
                for row in self._search_vector(query_vec, limit=limit * 2):
                    row = dict(row)
                    vec_score = row.pop("_vec_score", 0.0)
                    if vec_score < VECTOR_MIN_SCORE:
                        continue
                    score = vec_score + 0.1 * int(row.get("importance", 1))
                    existing = scored.get(row["id"])
                    if existing is None or score > existing.get("score", 0):
                        row["score"] = score
                        row["match"] = "semantic" if existing is None else "keyword+semantic"
                        scored[row["id"]] = row

        results = sorted(scored.values(), key=lambda r: r.get("score", 0), reverse=True)
        return results[:limit]

    def _search_keyword(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        terms = [f"%{t.strip().lower()}%" for t in query.split() if len(t.strip()) > 2]
        if not terms:
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

    def _search_vector(self, query_vec: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        """Recuerdos ordenados por similitud coseno con el vector de la consulta."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, created_at, category, summary, details, tags, importance, embedding
                FROM memories
                WHERE embedding IS NOT NULL
            """)
            rows = cursor.fetchall()
        scored = []
        for r in rows:
            row = dict(r)
            try:
                vec = _blob_to_vector(row["embedding"])
            except Exception:
                continue
            score = cosine_similarity(query_vec, vec)
            row["_vec_score"] = score
            row.pop("embedding", None)
            scored.append(row)
        scored.sort(key=lambda r: r["_vec_score"], reverse=True)
        return scored[:limit]

    def find_similar(self, summary: str, details: str = "", embedder=None) -> Optional[Dict[str, Any]]:
        """
        Busca un recuerdo ya guardado muy parecido a este (para no duplicar).
        Devuelve el recuerdo existente o None.
        """
        emb = embedder if embedder is not None else self.embedder
        # 1. Similitud semántica (la más fiable).
        if emb is not None:
            vec = emb.embed(f"{summary}. {details}".strip(". "))
            if vec:
                for row in self._search_vector(vec, limit=3):
                    if row.get("_vec_score", 0) >= DEDUP_VECTOR_SCORE:
                        row.pop("_vec_score", None)
                        row.pop("embedding", None)
                        return row
        # 2. Coincidencia de términos (sin embedder o como respaldo).
        new_terms = set(_normalize_terms(f"{summary} {details}"))
        if not new_terms:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, created_at, category, summary, details, tags, importance
                FROM memories
                ORDER BY created_at DESC
                LIMIT 50
            """)
            rows = cursor.fetchall()
        for r in rows:
            row = dict(r)
            old_terms = set(_normalize_terms(f"{row['summary']} {row.get('details') or ''}"))
            if not old_terms:
                continue
            overlap = len(new_terms & old_terms) / max(len(new_terms), 1)
            if overlap >= 0.8:
                return row
        return None

    def delete_memory(self, memory_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_by_query(self, query: str, limit: int = 5) -> List[int]:
        """Borra los recuerdos que coinciden con la consulta. Devuelve los IDs borrados."""
        matches = self.search_memories(query, limit=limit)
        deleted = []
        for m in matches:
            if self.delete_memory(m["id"]):
                deleted.append(m["id"])
        return deleted

    def count_memories(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM memories")
            return cursor.fetchone()[0]

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
