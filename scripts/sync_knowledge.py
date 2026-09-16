#!/usr/bin/env python3
"""Copy the authoritative documents of the owner's repositories into the pack.

    python scripts/sync_knowledge.py                 # repos are siblings of this checkout
    python scripts/sync_knowledge.py --repos-root ~/src

The digests under knowledge/<domain>/ are written by hand and say what a
senior engineer would remember. This script keeps the *verbatim* sources next
to them — each repository's constitution (CLAUDE.md), its open items, and the
handful of documents the constitutions say to read — so a question can be
answered from the text that actually governs, at the commit it was copied from.

Every copy gets the pack header with the source path, the commit and today's
date, so a retrieved chunk can say how fresh it is. A file the privacy
detector classifies as RESTRICTED is refused, not copied: the pack is data the
assistant retrieves, and a secret in it would be a secret in every answer.

AI Helper still imports nothing from those repositories. This is a copy of
markdown, made on purpose, by the operator, and committed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent / "knowledge"
sys.path.insert(0, str(HERE.parent))

# domain -> (repository directory name, GitHub name, [(relative path, title)])
SOURCES: dict[str, tuple[str, str, list[tuple[str, str]]]] = {
    "platform": (
        "Sniper-System",
        "sabuj14eu/Sniper-System",
        [
            ("CLAUDE.md", "Sniper-System platform constitution (CLAUDE.md)"),
            ("README.md", "Sniper-System platform README"),
            ("docs/OPEN_ITEMS.md", "Sniper-System open items (both sides)"),
            ("docs/HANDOFF_PLATFORM_SESSION.md", "Platform session handoff"),
            ("docs/V7_SELF_DEPENDENCE_PLAN.md", "V7 self-dependence master plan"),
            ("docs/INTEGRATION_V7.md", "Platform contract with the v7 bot"),
            ("docs/HANDOVER_V7_DESK.md", "Trade Desk handover for v7"),
        ],
    ),
    "v7": (
        "brother_sniper_v7",
        "sabuj14eu/brother_sniper_v7",
        [
            ("CLAUDE.md", "Brother Sniper v7 constitution (CLAUDE.md)"),
            ("INTENT_v5.md", "v7 trading intent (INTENT v5, symbol thesis and risk rules)"),
            ("ROADMAP.md", "v7 roadmap"),
            ("docs/V7_AUTONOMY_PLAN.md", "v7 autonomy plan"),
            ("docs/ADAPTIVE_GATES_SPEC.md", "v7 adaptive gates specification"),
            ("docs/START_HERE.md", "v7 bot: start here"),
            ("docs/OPEN_ITEMS.md", "v7 bot open items"),
            ("docs/STRATEGY_INTELLIGENCE.md", "v7 strategy intelligence"),
        ],
    ),
    "brain": (
        "brother-brain-v2",
        "sabuj14eu/brother-brain-v2",
        [
            ("CLAUDE.md", "v18 brain constitution (CLAUDE.md)"),
            ("README.md", "v18 brain README"),
            ("docs/OPEN_ITEMS.md", "v18 brain open items"),
            ("docs/decisions.md", "v18 brain decisions log"),
            ("docs/PROTOCOL.md", "v18 brain protocol"),
            ("docs/PINE_VS_BOT_MAP.md", "Pine versus bot map"),
        ],
    ),
    "developer": (
        "brother-developer",
        "sabuj14eu/brother-developer",
        [
            ("CLAUDE.md", "Brother Developer constitution (CLAUDE.md)"),
            ("README.md", "Brother Developer README"),
            ("docs/BROTHER_DEVELOPER.md", "Brother Developer master specification"),
            ("docs/SESSION_PROTOCOL.md", "Brother Developer session protocol"),
        ],
    ),
    "accounting": (
        "Accounting-",
        "sabuj14eu/Accounting-",
        [
            ("CLAUDE.md", "Accounting application constitution (CLAUDE.md)"),
            ("README.md", "Accounting application README"),
            ("docs/OPEN_ITEMS.md", "Accounting open items"),
            ("docs/ARCHITECTURE.md", "Accounting architecture"),
            ("docs/POLAND_TAX_ENGINE.md", "Poland tax engine"),
            ("docs/CHANGELOG.md", "Accounting changelog"),
        ],
    ),
}


def git_head(repo: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "UNKNOWN"


def strip_existing_header(text: str) -> str:
    """A source that already opens with a '---' block would double up."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5 :]
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repos-root", default=str(HERE.parent.parent))
    parser.add_argument("--out", default=str(PACK / "sources"))
    args = parser.parse_args(argv)

    from app.database.enums import Classification
    from app.knowledge.pack import secret_probe
    from app.privacy.classification import classify

    root = Path(args.repos_root).expanduser().resolve()
    out = Path(args.out).resolve()
    today = dt.date.today().isoformat()
    manifest: dict = {"synced_on": today, "repos_root": str(root), "files": []}
    refused: list[str] = []

    for domain, (dirname, github, files) in SOURCES.items():
        repo = root / dirname
        if not repo.is_dir():
            print(f"skip {domain}: {repo} not found", file=sys.stderr)
            continue
        commit = git_head(repo)
        target_dir = out / domain
        target_dir.mkdir(parents=True, exist_ok=True)
        for relative, title in files:
            source = repo / relative
            if not source.is_file():
                print(f"skip {domain}/{relative}: not in repository", file=sys.stderr)
                continue
            text = source.read_text(encoding="utf-8", errors="replace")
            # A documented placeholder such as `X-Brain-Secret: <BB_BRAIN_WEBHOOK_SECRET>`
            # is not a secret; classify with placeholders blanked, copy the text as is.
            verdict = classify(secret_probe(text), client_default=Classification.INTERNAL.value)
            if verdict.classification is Classification.RESTRICTED:
                refused.append(f"{domain}/{relative}")
                print(f"REFUSED {domain}/{relative}: looks like it holds a secret", file=sys.stderr)
                continue
            header = (
                "---\n"
                f"title: {title}\n"
                f"domain: {domain}\n"
                f"repo: {github}\n"
                f"sources: {relative}\n"
                f"verified_on: {today}\n"
                f"commit: {commit}\n"
                "classification: INTERNAL\n"
                "---\n\n"
            )
            name = relative.replace("/", "__")
            target = target_dir / name
            body = strip_existing_header(text)
            if target.is_file() and strip_existing_header(target.read_text(encoding="utf-8")) == body:
                # Unchanged text keeps its earlier header, so a re-sync does not
                # re-stamp (and re-ingest) a document nobody edited.
                print(f"unchanged {domain}/{name}")
            else:
                target.write_text(header + body, encoding="utf-8")
                print(f"synced {domain}/{name} @ {commit}")
            manifest["files"].append(
                {"domain": domain, "path": f"{domain}/{name}", "from": f"{dirname}/{relative}", "commit": commit}
            )

    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(manifest['files'])} files synced, {len(refused)} refused, manifest at {out / 'MANIFEST.json'}")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
