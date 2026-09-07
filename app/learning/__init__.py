"""Learning: capture hard cases, and promote only what survives the gates."""

from app.learning.fallback_capture import CaptureDecision, capture
from app.learning.promotion import PromotionOutcome, PromotionPipeline
from app.learning.similarity import fingerprint, jaccard, normalise
from app.learning.solution_store import SolutionStore

__all__ = [
    "capture",
    "CaptureDecision",
    "PromotionPipeline",
    "PromotionOutcome",
    "SolutionStore",
    "fingerprint",
    "jaccard",
    "normalise",
]
