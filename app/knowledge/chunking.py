"""Chunking.

Splits on the largest structural boundary that fits — paragraph, then
sentence, then word — so a chunk rarely begins mid-sentence. Overlap carries
the tail of one chunk into the next, so a fact that straddles a boundary is
retrievable from either side.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    ordinal: int
    content: str
    start: int
    end: int

    @property
    def char_count(self) -> int:
        return len(self.content)


def _split_long(text: str, size: int) -> list[str]:
    """Break a single oversized block on sentence, then word, boundaries."""
    if len(text) <= size:
        return [text]
    pieces: list[str] = []
    buffer = ""
    for sentence in _SENTENCE.split(text):
        if not sentence:
            continue
        if len(buffer) + len(sentence) + 1 <= size:
            buffer = f"{buffer} {sentence}".strip()
            continue
        if buffer:
            pieces.append(buffer)
            buffer = ""
        if len(sentence) <= size:
            buffer = sentence
            continue
        words = sentence.split()
        for word in words:
            if len(buffer) + len(word) + 1 <= size:
                buffer = f"{buffer} {word}".strip()
            else:
                if buffer:
                    pieces.append(buffer)
                # A single token longer than the chunk size is cut; there is
                # no boundary left to respect.
                buffer = word if len(word) <= size else ""
                if len(word) > size:
                    pieces.extend(word[i : i + size] for i in range(0, len(word), size))
    if buffer:
        pieces.append(buffer)
    return pieces


def chunk_text(text: str, *, size: int = 900, overlap: int = 150) -> list[Chunk]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    overlap = max(0, min(overlap, size // 2))
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    blocks: list[str] = []
    for paragraph in _PARAGRAPH.split(cleaned):
        paragraph = paragraph.strip()
        if paragraph:
            blocks.extend(_split_long(paragraph, size))

    chunks: list[Chunk] = []
    buffer = ""
    for block in blocks:
        if not buffer:
            buffer = block
        elif len(buffer) + len(block) + 2 <= size:
            buffer = f"{buffer}\n\n{block}"
        else:
            chunks.append(buffer)
            tail = buffer[-overlap:] if overlap else ""
            # Start the overlap at a word boundary so it reads as text.
            if tail and " " in tail:
                tail = tail[tail.index(" ") + 1 :]
            # The overlap is a courtesy, not a licence to exceed the size: a
            # block that is already full-size carries no tail.
            if tail and len(tail) + len(block) + 2 > size:
                tail = ""
            buffer = f"{tail}\n\n{block}".strip() if tail else block
    if buffer:
        chunks.append(buffer)

    out: list[Chunk] = []
    cursor = 0
    for index, content in enumerate(chunks):
        start = cleaned.find(content[:60], cursor)
        if start == -1:
            start = cursor
        out.append(Chunk(ordinal=index, content=content, start=start, end=start + len(content)))
        cursor = max(cursor, start + max(1, len(content) - overlap))
    return out
