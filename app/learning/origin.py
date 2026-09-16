"""Where a solution came from — which is not the same question as how good it is.

The dashboard read "229 learned solutions" and every one of them was
hand-written. They are pack seeds: a session wrote the question and the answer
into `knowledge/`, and the promotion gate confirmed the local model could
restate them. That is a real and useful thing, but it is *authoring*, not
learning, and counting it as learning made the system look like it was getting
better with use when it had never learned anything from being used at all.

Status already says how far a solution got. This says where it started, and
the two together are what an honest count needs:

    SEEDED  someone wrote it into the pack and a session loaded it
    TAUGHT  the owner corrected Brother, in his own words
    SELF    Brother answered, the answer passed validation, and it was kept
    PAID    a paid provider answered a question the local model could not

No column is added. The origin is derived from `provider`, which every row has
carried since 1.0 — so this is a reading of data already recorded, not a
migration, and it is correct for rows written before it existed.
"""

from __future__ import annotations

from enum import StrEnum

from app.knowledge.pack import PACK_SOURCE
from app.learning.teaching import TAUGHT_PROVIDER

SELF_PROVIDER = "local-verified"


class SolutionOrigin(StrEnum):
    SEEDED = "seeded"
    TAUGHT = "taught"
    SELF = "self"
    PAID = "paid"


LABELS = {
    SolutionOrigin.SEEDED: "written into the pack by a session",
    SolutionOrigin.TAUGHT: "taught by the owner",
    SolutionOrigin.SELF: "Brother's own answer, kept after it passed validation",
    SolutionOrigin.PAID: "answered by a paid provider",
}


def origin_of(provider: str | None) -> SolutionOrigin:
    """Which of the four a row came from. Anything unrecognised is PAID.

    PAID is the safe default for an unknown provider: it is the only origin
    that implies the answer came from outside, so guessing it errs toward
    treating a row as less trusted rather than more.
    """
    name = (provider or "").strip().lower()
    if name == PACK_SOURCE:
        return SolutionOrigin.SEEDED
    if name == TAUGHT_PROVIDER:
        return SolutionOrigin.TAUGHT
    if name == SELF_PROVIDER:
        return SolutionOrigin.SELF
    return SolutionOrigin.PAID


def summarise(rows) -> dict[str, int]:
    """Count rows by origin. Every origin appears, including the empty ones.

    A zero that is shown is a fact; a zero that is omitted looks like a
    category nobody thought about, and `self: 0` is exactly the number this
    module exists to make visible.
    """
    counts = {origin.value: 0 for origin in SolutionOrigin}
    for row in rows:
        counts[origin_of(getattr(row, "provider", None)).value] += 1
    return counts
