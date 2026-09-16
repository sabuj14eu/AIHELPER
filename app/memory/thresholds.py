"""Similarity thresholds, chosen for the embedder that is actually running."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.memory.embeddings import Embedder


@dataclass(frozen=True)
class Thresholds:
    memory: float
    solution_reuse: float
    solution_duplicate: float
    embedder_id: str
    semantic: bool

    def as_dict(self) -> dict:
        return {
            "embedder": self.embedder_id,
            "semantic": self.semantic,
            "memory_similarity": self.memory,
            "solution_reuse": self.solution_reuse,
            "solution_duplicate": self.solution_duplicate,
        }


def for_embedder(embedder: Embedder, settings: Settings) -> Thresholds:
    if embedder.semantic:
        return Thresholds(
            memory=settings.MEMORY_SIMILARITY_THRESHOLD,
            solution_reuse=settings.SOLUTION_REUSE_THRESHOLD,
            solution_duplicate=settings.SOLUTION_DUPLICATE_THRESHOLD,
            embedder_id=embedder.id,
            semantic=True,
        )
    return Thresholds(
        memory=settings.LEXICAL_MEMORY_SIMILARITY_THRESHOLD,
        solution_reuse=settings.LEXICAL_SOLUTION_REUSE_THRESHOLD,
        solution_duplicate=settings.LEXICAL_SOLUTION_DUPLICATE_THRESHOLD,
        embedder_id=embedder.id,
        semantic=False,
    )
