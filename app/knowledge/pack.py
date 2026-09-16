"""The knowledge pack — how AI Helper learns who it works for.

A pack is a directory of markdown files, each opening with a small header:

    ---
    title: Freshness Law
    domain: platform
    repo: sabuj14eu/Sniper-System
    sources: CLAUDE.md, docs/HANDOFF_PLATFORM_SESSION.md
    verified_on: 2026-09-16
    classification: INTERNAL
    ---

Loading a pack ingests every file as a document of the owning client, in the
namespace named by ``domain``, through the ordinary ingestion pipeline: the
same chunking, the same embedder, the same index, the same audit row. Nothing
here is a second path into retrieval — a pack document is a document.

Two rules that matter:

* **A changed file replaces its document; an unchanged file is a no-op.** The
  file's own digest is kept in ``Document.meta`` so a reload is idempotent and
  a stale copy never sits next to the fresh one contradicting it.
* **Validated solutions are seeded through the promotion gate, never around
  it.** A ``*validated_solutions.md`` file carries question/answer/evidence
  blocks. Each becomes a CANDIDATE row and is handed to the same
  :class:`PromotionPipeline` a paid answer goes through. With a local model
  running they end PROMOTED; without one they are held at VALIDATED, exactly
  as any other candidate would be. The evidence pointer travels on the row.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import KNOWLEDGE_PACK_LOADED, record
from app.core.logging import get_logger
from app.database.enums import Classification, DocumentStatus, SolutionStatus
from app.database.models import Document
from app.knowledge.ingestion import DocumentIngestor
from app.learning.solution_store import SolutionStore

log = get_logger("knowledge.pack")

PACK_SOURCE = "knowledge-pack"
_HEADER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SOLUTION_BLOCK = re.compile(
    r"^###\s+(?P<title>[^\n]+)\n"
    r"(?:[ \t]*\n)*"
    r"question:\s*(?P<question>[^\n]+)\n"
    r"answer:\s*(?P<answer>.*?)\n"
    r"evidence:\s*(?P<evidence>[^\n]+)",
    re.MULTILINE | re.DOTALL,
)


class PackError(ValueError):
    """A pack file that cannot be loaded as written."""


@dataclass(frozen=True)
class PackHeader:
    title: str
    domain: str
    repo: str = ""
    sources: str = ""
    verified_on: str = ""
    classification: str = Classification.INTERNAL.value
    commit: str = ""

    def as_meta(self) -> dict:
        return {
            "title": self.title,
            "domain": self.domain,
            "repo": self.repo,
            "sources": self.sources,
            "verified_on": self.verified_on,
            "commit": self.commit,
        }


@dataclass(frozen=True)
class PackFile:
    path: Path
    relative: str
    header: PackHeader
    body: str
    sha256: str

    @property
    def is_solutions_file(self) -> bool:
        return self.path.name.endswith("validated_solutions.md")


@dataclass(frozen=True)
class SeedSolution:
    title: str
    question: str
    answer: str
    evidence: str
    source_file: str
    domain: str


@dataclass
class LoadReport:
    client_id: str
    root: str
    ingested: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    chunks: int = 0
    solutions: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "root": self.root,
            "ingested": len(self.ingested),
            "replaced": len(self.replaced),
            "unchanged": len(self.unchanged),
            "removed": len(self.removed),
            "failed": dict(self.failed),
            "chunks": self.chunks,
            "solutions": dict(self.solutions),
            "files": {
                "ingested": list(self.ingested),
                "replaced": list(self.replaced),
                "removed": list(self.removed),
            },
        }


# ------------------------------------------------------------------ parsing
def parse_header(text: str, *, path: str = "<memory>") -> tuple[PackHeader, str]:
    """Split a pack file into its header and body. Missing header is an error."""
    match = _HEADER.match(text)
    if match is None:
        raise PackError(f"{path}: a pack file must open with a '---' header block")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    title = fields.get("title", "")
    domain = fields.get("domain", "")
    if not title or not domain:
        raise PackError(f"{path}: the header needs both 'title' and 'domain'")
    classification = fields.get("classification", Classification.INTERNAL.value).upper()
    try:
        classification = Classification(classification).value
    except ValueError as exc:
        raise PackError(f"{path}: unknown classification '{classification}'") from exc
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,60}", domain):
        raise PackError(f"{path}: domain '{domain}' must be a short lowercase slug")
    header = PackHeader(
        title=title,
        domain=domain,
        repo=fields.get("repo", ""),
        sources=fields.get("sources", ""),
        verified_on=fields.get("verified_on", ""),
        classification=classification,
        commit=fields.get("commit", ""),
    )
    return header, text[match.end() :].strip()


def parse_solutions(body: str, *, source_file: str, domain: str) -> list[SeedSolution]:
    """Pull question/answer/evidence blocks out of a validated-solutions file."""
    out: list[SeedSolution] = []
    for match in _SOLUTION_BLOCK.finditer(body):
        answer = " ".join(line.strip() for line in match.group("answer").splitlines()).strip()
        question = match.group("question").strip()
        evidence = match.group("evidence").strip()
        if not question or not answer:
            continue
        out.append(
            SeedSolution(
                title=match.group("title").strip(),
                question=question,
                answer=answer,
                evidence=evidence,
                source_file=source_file,
                domain=domain,
            )
        )
    return out


def discover(root: Path) -> list[PackFile]:
    """Every markdown file under the root, parsed. A bad file raises."""
    root = Path(root)
    if not root.is_dir():
        raise PackError(f"knowledge pack directory not found: {root}")
    files: list[PackFile] = []
    for path in sorted(root.rglob("*.md")):
        # The pack's own README describes the pack; it is not knowledge.
        if path.parent == root and path.name.upper() == "README.MD":
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        header, body = parse_header(text, path=str(path))
        files.append(
            PackFile(
                path=path,
                relative=path.relative_to(root).as_posix(),
                header=header,
                body=body,
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    return files


def render_for_ingestion(pack_file: PackFile) -> bytes:
    """The text that is chunked: a one-paragraph provenance banner, then the body.

    The banner is the first thing in the first chunk, so a retrieved opening
    chunk says where it came from; later chunks rely on the pack's own rule
    that every section names its subject.
    """
    header = pack_file.header
    banner = (
        f"Knowledge pack document: {header.title}. Domain: {header.domain}."
        + (f" Repository: {header.repo}." if header.repo else "")
        + (f" Sources: {header.sources}." if header.sources else "")
        + (f" Verified on: {header.verified_on}." if header.verified_on else "")
        + (f" Commit: {header.commit}." if header.commit else "")
    )
    return f"{banner}\n\n{pack_file.body}\n".encode()


# ------------------------------------------------------------------ loading
class KnowledgePackLoader:
    def __init__(self, session: Session, client_id: str, *, ingestor: DocumentIngestor):
        self.session = session
        self.client_id = client_id
        self.ingestor = ingestor

    def existing(self) -> dict[str, Document]:
        """Pack documents already held by this client, by pack path."""
        stmt = select(Document).where(Document.client_id == self.client_id)
        out: dict[str, Document] = {}
        for document in self.session.scalars(stmt):
            meta = document.meta or {}
            if meta.get("source") == PACK_SOURCE and meta.get("pack_path"):
                out[meta["pack_path"]] = document
        return out

    def load(self, root: Path, *, prune: bool = False) -> LoadReport:
        root = Path(root)
        report = LoadReport(client_id=self.client_id, root=str(root))
        files = discover(root)
        held = self.existing()
        seen: set[str] = set()

        for pack_file in files:
            seen.add(pack_file.relative)
            previous = held.get(pack_file.relative)
            if previous is not None and (previous.meta or {}).get("pack_sha") == pack_file.sha256:
                report.unchanged.append(pack_file.relative)
                continue
            if previous is not None:
                self.ingestor.delete(previous.id)
                self.session.flush()
            try:
                result = self.ingestor.ingest(
                    render_for_ingestion(pack_file),
                    pack_file.path.name,
                    namespace=pack_file.header.domain,
                    classification=pack_file.header.classification,
                    title=pack_file.header.title,
                    meta={
                        "source": PACK_SOURCE,
                        "pack_path": pack_file.relative,
                        "pack_sha": pack_file.sha256,
                        **pack_file.header.as_meta(),
                    },
                )
            except Exception as exc:
                report.failed[pack_file.relative] = f"{type(exc).__name__}: {exc}"[:300]
                log.error("pack_file_failed", path=pack_file.relative, error=type(exc).__name__)
                continue
            if result.document.status != DocumentStatus.READY.value:
                report.failed[pack_file.relative] = result.document.error or "not READY"
            report.chunks += result.chunks
            (report.replaced if previous is not None else report.ingested).append(pack_file.relative)

        if prune:
            for path, document in held.items():
                if path not in seen:
                    self.ingestor.delete(document.id)
                    report.removed.append(path)
            # Autoflush is off: a status read in the same session must not
            # still see the rows this just removed.
            self.session.flush()

        record(
            self.session,
            actor=self.client_id,
            action=KNOWLEDGE_PACK_LOADED,
            resource_type="knowledge_pack",
            resource_id=str(root)[:200],
            detail={
                "ingested": len(report.ingested),
                "replaced": len(report.replaced),
                "unchanged": len(report.unchanged),
                "removed": len(report.removed),
                "failed": len(report.failed),
            },
        )
        return report

    def status(self, root: Path | None = None) -> dict:
        """What the client holds, and how it compares to the pack on disk."""
        held = self.existing()
        by_domain: dict[str, dict[str, int]] = {}
        for document in held.values():
            bucket = by_domain.setdefault(document.namespace, {"documents": 0, "chunks": 0})
            bucket["documents"] += 1
            bucket["chunks"] += document.chunk_count or 0
        out: dict = {
            "client_id": self.client_id,
            "documents": len(held),
            "by_domain": by_domain,
            "solutions": SolutionStore(self.session, self.client_id).counts(),
        }
        if root is not None and Path(root).is_dir():
            on_disk = {f.relative: f for f in discover(Path(root))}
            stale = [
                path
                for path, document in held.items()
                if path in on_disk and (document.meta or {}).get("pack_sha") != on_disk[path].sha256
            ]
            out["pack"] = {
                "root": str(root),
                "files_on_disk": len(on_disk),
                "missing_from_client": sorted(set(on_disk) - set(held)),
                "stale_in_client": sorted(stale),
                "orphaned_in_client": sorted(set(held) - set(on_disk)),
            }
        return out


# ------------------------------------------------------------------ seeding
def seed_solutions(
    session: Session,
    client_id: str,
    files: list[PackFile],
    *,
    pipeline=None,
    ttl_days: int | None = None,
) -> dict[str, int]:
    """Turn validated-solution blocks into candidates and run them through the gate.

    Returns counts by outcome. A question already known to the store — in any
    status — is skipped, so reloading never duplicates a row or resurrects a
    rejection.
    """
    store = SolutionStore(session, client_id)
    counts = {"seeded": 0, "skipped": 0, "promoted": 0, "validated": 0, "rejected": 0}
    for pack_file in files:
        if not pack_file.is_solutions_file:
            continue
        for seed in parse_solutions(
            pack_file.body, source_file=pack_file.relative, domain=pack_file.header.domain
        ):
            if store.by_fingerprint(seed.question):
                counts["skipped"] += 1
                continue
            solution = store.create(
                question=seed.question,
                answer=seed.answer,
                task_type="general",
                provider=PACK_SOURCE,
                model=pack_file.header.repo or seed.domain,
                failure_reason=None,
                local_attempt=None,
                validation_result={
                    "seed": {
                        "title": seed.title,
                        "evidence": seed.evidence,
                        "source_file": seed.source_file,
                        "verified_on": pack_file.header.verified_on,
                    }
                },
                confidence=0.0,
                classification=pack_file.header.classification,
                context={
                    "texts": [f"{seed.title}\n{seed.answer}\nEvidence: {seed.evidence}"],
                    "sources": [{"source": PACK_SOURCE, "ref": seed.source_file}],
                },
                ttl_days=ttl_days,
            )
            counts["seeded"] += 1
            if pipeline is None:
                continue
            outcome = pipeline.process(solution)
            if outcome.status is SolutionStatus.PROMOTED:
                counts["promoted"] += 1
            elif outcome.status is SolutionStatus.VALIDATED:
                counts["validated"] += 1
            else:
                counts["rejected"] += 1
    return counts
