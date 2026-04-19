"""
Local 384-dim sentence embedder.

Uses ``sentence-transformers/all-MiniLM-L6-v2``. First call downloads the
model (~25MB) into the user's HuggingFace cache. After that every encode
runs locally with no network traffic.
"""

from __future__ import annotations

import logging
import struct
from typing import Iterable

log = logging.getLogger("pilotd.embedding")

EMBED_DIM = 384
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder:
    """Singleton-style lazy loader around SentenceTransformer."""

    _model = None  # class-level so repeated construction shares one model

    def encode(self, text: str) -> list[float]:
        self._ensure_model()
        assert Embedder._model is not None
        emb = Embedder._model.encode(text, normalize_embeddings=True)
        return [float(x) for x in emb.tolist()]

    @classmethod
    def _ensure_model(cls) -> None:
        if cls._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for local embeddings. "
                "Install: pip install sentence-transformers"
            ) from exc
        log.info("Loading embedding model %s", MODEL_NAME)
        cls._model = SentenceTransformer(MODEL_NAME)


def pack_vector(vec: Iterable[float]) -> bytes:
    """Pack a float vector into sqlite-vec's little-endian float32 bytes format."""
    values = list(vec)
    if len(values) != EMBED_DIM:
        raise ValueError(f"Expected {EMBED_DIM}-dim vector, got {len(values)}")
    return struct.pack(f"{EMBED_DIM}f", *values)
