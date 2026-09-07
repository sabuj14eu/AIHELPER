"""Embeddings.

Two implementations, and the difference between them matters enough to state
plainly:

* :class:`OllamaEmbedder` produces real semantic embeddings from a local
  model. This is what a deployment should run.
* :class:`HashingEmbedder` is a deterministic **lexical** vectoriser — hashed
  word unigrams and bigrams, sublinear term frequency, L2-normalised. It has
  no semantic understanding at all: it will match "what is the VAT rate" to
  "what's the VAT rate?" and will NOT match it to "how much sales tax do I
  charge". It exists so the system is fully functional and fully testable with
  no model server running, and so a broken embedding model degrades retrieval
  instead of taking the gateway down.

Every vector is tagged with the id of the embedder that produced it, and
vectors from different embedders are never compared: they live in separate
collections. Changing EMBEDDING_MODEL therefore invalidates nothing — it
starts a new collection, and the old one is simply no longer read.
"""

from __future__ import annotations

import abc
import hashlib
import math
import re
from collections import Counter

from app.core.logging import get_logger
from app.local_ai.model_manager import ModelManager
from app.local_ai.ollama_client import OllamaClient

log = get_logger("embeddings")

_WORD = re.compile(r"[A-Za-zÀ-ž0-9_]+")


class Embedder(abc.ABC):
    """Turns text into a unit-length vector."""

    id: str = "embedder"
    dim: int = 0
    semantic: bool = False

    @abc.abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


def l2_normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Both inputs are assumed unit-length; guarded anyway."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))  # lengths checked above
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


class HashingEmbedder(Embedder):
    """Deterministic lexical vectoriser. Offline fallback — not semantic."""

    semantic = False

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.id = f"hash-v1-{dim}"

    @staticmethod
    def _features(text: str) -> Counter:
        words = [w.lower() for w in _WORD.findall(text or "")]
        features = Counter(words)
        features.update(f"{a}_{b}" for a, b in zip(words, words[1:], strict=False))  # bigrams: one shorter by design
        return features

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dim
            for feature, count in self._features(text).items():
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] & 1 else -1.0
                # Sublinear tf: a word repeated ten times is not ten times as
                # important as one used once.
                vector[index] += sign * (1.0 + math.log(count))
            out.append(l2_normalise(vector))
        return out


class OllamaEmbedder(Embedder):
    """Real embeddings from a local Ollama model."""

    semantic = True

    def __init__(self, client: OllamaClient, model: str, dim: int):
        self.client = client
        self.model = model
        self.dim = dim
        self.id = f"ollama-{model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.client.embed(self.model, texts)
        if not vectors or len(vectors) != len(texts):
            raise ValueError("embedding model returned the wrong number of vectors")
        if self.dim and len(vectors[0]) != self.dim:
            # Trust the model over the configured number, and say so once.
            log.warning(
                "embedding_dim_mismatch", configured=self.dim, actual=len(vectors[0]), model=self.model
            )
            self.dim = len(vectors[0])
        return [l2_normalise(v) for v in vectors]


def build_embedder(
    model_manager: ModelManager | None,
    ollama_client: OllamaClient | None,
    *,
    configured_dim: int = 768,
    fallback_dim: int = 512,
) -> Embedder:
    """Use the real embedding model if it is installed; otherwise fall back.

    The fallback is announced in the log and reported by /health, so nobody
    has to guess which one is in use.
    """
    if model_manager is not None and ollama_client is not None:
        model = model_manager.select_embedding_model()
        if model:
            embedder = OllamaEmbedder(ollama_client, model, configured_dim)
            try:
                embedder.embed(["probe"])
                log.info("embedder_selected", embedder=embedder.id, semantic=True)
                return embedder
            except Exception as exc:
                log.warning(
                    "embedding_model_unusable",
                    model=model,
                    error=type(exc).__name__,
                    falling_back_to="hashing",
                )
    log.warning(
        "using_lexical_fallback_embedder",
        detail="no usable embedding model; semantic search degrades to lexical matching",
    )
    return HashingEmbedder(fallback_dim)
