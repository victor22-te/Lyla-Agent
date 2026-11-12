"""
Embeddings semánticos para la memoria episódica de LYLA.

Usa Gemini text-embedding-004 (free tier, cloud-first, igual que el LLM).
Si no hay API key o falla la red, devuelve None y la búsqueda cae al modo
por palabras clave — la memoria nunca se rompe por falta de embeddings.
"""
import os
from typing import List, Optional

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIM = 768


class GeminiEmbedder:
    """Genera embeddings con Gemini. Ligero: el cliente se crea solo al primer uso."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._client = None
        self.enabled = bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def embed(self, text: str) -> Optional[List[float]]:
        """Vector del texto (768 dims) o None si no se pudo generar."""
        text = (text or "").strip()
        if not text or not self.enabled:
            return None
        try:
            client = self._get_client()
            result = client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
            values = result.embeddings[0].values
            return [float(v) for v in values]
        except Exception as e:
            print(f"[Memoria] Embedding falló, usando búsqueda por palabras clave: {e}")
            return None

    def embed_many(self, texts: List[str]) -> List[Optional[List[float]]]:
        return [self.embed(t) for t in texts]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Similitud coseno en Python puro (sin numpy). 1 = idénticos, 0 = sin relación."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))
