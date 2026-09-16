# The knowledge pack

This directory is what makes AI Helper *Brother* — the owner's own assistant —
instead of a generic gateway. It is data, loaded through the ordinary document
pipeline, and the code never imports anything from the repositories it
describes.

```
knowledge/
├── brother/       who Brother is, the working laws, the map of every project, the toolchain,
│                  the social-media publishing rules            (hand-written, this repo)
├── platform/      Sniper-System: the SaaS platform, Trade Desk, evidence tables, Pine workspace
├── brain/         brother-brain-v2: the v18 council, dispatch, executors, dashboard
├── v7/            brother_sniper_v7: the mechanical arm, news gate, bridge, posting tools
├── developer/     brother-developer: the read-only engineering agent, ADRs, ledger
├── accounting/    Accounting-: the Polish JDG tax engine and the shop-intelligence app
└── sources/       verbatim copies of each repository's governing documents, stamped with
                   the commit they were copied from   (scripts/sync_knowledge.py writes these)
```

Each domain folder holds eight digests: `overview`, `laws`, `architecture`,
`evidence`, `workflows_and_tools`, `validated_solutions`, `open_items`,
`glossary`. The digests are what a senior engineer would remember; `sources/`
is what the repositories actually say. When they disagree, the source wins and
the digest is wrong — fix the digest.

## File format

Every file opens with a header the loader parses:

```
---
title: Freshness Law
domain: platform
repo: sabuj14eu/Sniper-System
sources: CLAUDE.md, docs/HANDOFF_PLATFORM_SESSION.md
verified_on: 2026-09-16
classification: INTERNAL
---
```

`title` and `domain` are required; `domain` becomes the document namespace.
The body is plain markdown in short, self-contained paragraphs: it is chunked
at about 900 characters, so every section names its subject ("The v7 bot's
news gate …", never "It …").

A file whose name ends in `validated_solutions.md` also carries blocks the
loader turns into learned solutions:

```
### One tick cannot fix a clock
question: Why were candles stamped an hour late on 2026-08-20?
answer: The reporter read one tick during the metals rollover break and …
evidence: CLAUDE.md "A CLOCK NEEDS TWO WITNESSES"; agents/mt5_reporter.detect_broker_offset
```

Each block becomes a CANDIDATE and goes through the same promotion gate as a
paid answer (validation, then reproduction by the local model). With a local
model running they end PROMOTED; without one they are held at VALIDATED and
are still retrievable as document text.

## Rules

- **No secrets.** Never a token, password, key, secret header value or `.env`
  value. `scripts/sync_knowledge.py` refuses a file the privacy detector
  classifies as RESTRICTED; the digests were written under the same rule.
- **Facts carry provenance.** Every non-obvious claim names its source file,
  and every file carries `verified_on`. Where a repository is silent the
  digest says UNKNOWN. A number without its source and date is not knowledge.
- **A changed file replaces its document.** The loader keys on the file path
  and its digest; an unchanged file is a no-op, a changed one is re-ingested,
  and `--prune` removes documents whose file is gone.

## Loading and refreshing

```bash
python -m app.cli bootstrap-brother          # first time: creates the client, loads, seeds
python scripts/sync_knowledge.py             # refresh sources/ from the sibling checkouts
python -m app.cli load-knowledge --prune     # re-ingest what changed
python -m app.cli knowledge-status           # what the assistant holds vs. what is on disk
```

Digests are refreshed by hand when a repository's laws or evidence change —
that is a session task, and `docs/BROTHER.md` says how.
