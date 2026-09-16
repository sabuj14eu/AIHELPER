---
title: Platform session handoff
domain: platform
repo: sabuj14eu/Sniper-System
sources: docs/HANDOFF_PLATFORM_SESSION.md
verified_on: 2026-09-16
commit: 3257184
classification: INTERNAL
---

# HANDOFF — the platform session (written 2026-09-02, v5.17)

This is for the NEXT Claude window. The previous one grew too heavy to
continue. State below is as of v5.24. Read CLAUDE.md first (the laws), then this file (the state and
the habits), then `docs/OPEN_ITEMS.md` (the debts). Do not start work
until you have read all three.

---

## 1. WHAT YOU OWN, AND WHAT YOU DO NOT

You own the **PLATFORM / UI side only**: this repository
(`sabuj14eu/Sniper-System`, deployed at `/srv/brotherbot` on the Linux
box, served at app.signalmesh.dev). Branch:
`claude/brother-bot-trading-platform-58o7gr`.

**The bot and brain side is owned by ANOTHER session.** Do not touch
`/home/shyam/brain-v2` or `/home/shyam/brother_sniper_v7`, and do not
propose changes to them. When a finding is theirs, say so in one line
and hand it over; do not fix it from here. You may READ their repos to
explain what a log line means. Reading is not touching.

**Never `git checkout` a different branch on the box.** The services
load whatever the checkout says on next restart. Need one file from
another branch: `git checkout origin/<branch> -- path/to/file.py`.

**Never activate any live stop movement.** Nothing on this platform
places, modifies or closes an order, and nothing you build may.

**Never create a pull request unless Shyam explicitly asks for one.**

---

## 2. HOW SHYAM WORKS, AND THEREFORE HOW YOU WRITE

He pastes into a terminal. He will not fill in blanks.

- **One paste per step. No placeholders, ever.** Not `<your-path>`, not
  `<symbol>`. If a value is needed, you already know it or you ask.
- **Start every block with `cd /absolute/path && ...`.**
- **Name the box on the line above the block:** `Linux box: vmi3221804`.
- **Say what correct output looks like** after every block, so he can
  tell success from failure without asking you.
- **Run `pytest -q` before every commit.** The full suite, not a subset.
  Report the count. If it fails, say so with the output.

He reads screens the way an auditor reads a ledger, and he is very good
at it. Three days running he found real bugs by noticing two numbers
on one page that could not both be true. **When he pastes a screen and
says something is wrong, he is nearly always right, and the bug is
nearly always bigger than the sentence he wrote.** Trace it in code
before answering. Never explain a paste away.

His English is direct and compressed ("is all done sir?", "Please sir
fix"). Answer the question he asked, first, in one line. Then the
detail. He says "sir" out of courtesy; you do not need to.

The standing deploy line (no migration unless the CHANGELOG says so):

```
cd /srv/brotherbot && git pull && docker compose up -d --build app && sleep 20 && docker compose logs --tail 30 app
```

Correct output: `Uvicorn running` / `Application startup complete`, no
traceback, the version chip on any page reads the new VERSION.

---

## 3. THE STATE ON HANDOFF

- **v5.24 ready; v5.23 live, migration applied 2026-09-03 10:35 UTC**
  (8 twins removed, index present, ghost cleared). 723 tests. Nothing
  pending.
- **v5.00–v5.17 in one breath:** the observability milestone
  (`/admin/engineering`, seven deterministic watchers, incident
  lifecycle), `/brain-view`, NVDA onboarded, the Trade Desk split into
  a live page and an Evidence Lab (`/evidence`), and then three days of
  fixing screens that were arguing with themselves. Read CHANGELOG
  5.16 and 5.17 in full — they are the best description of how this
  system fails and how to fix it.
- **FAIL-SOFT is now visible (v5.18).** The bot session added
  `fail_soft` / `fail_soft_reason` / `fail_soft_count` to every mirrored
  decision row; the platform reads them in `services/fail_soft` and
  renders `TRADED WITHOUT COUNCIL, fail-soft n/2` on every decision
  row, everywhere. The policy itself is the brain's (audit P1-1, 07-31:
  approve on Pine trust when the council API errors on an A/A+, at most
  `FAILSOFT_MAX_PER_DAY=2` per UTC day, then fail closed). Whether to
  keep that bounded exception to Iron Rule 1 is Shyam's call.

## 4. PENDING — SHYAM'S, NO DEADLINE

Two MT5 clicks (GOLD #1900277473 close; SILVER orphan stop). INC-0001
APPROVE/RESOLVE, INC-0003 RESOLVE on `/admin/engineering`. DD-guard numbers. PLAT-EXPOSURE-1
(NVDA+US100 as one exposure).

## 5. PENDING — YOURS, WHEN ASKED

- Identity journal (B9 — needs a new table and a migration).
- Spread history (A5 — schema).
- PLAT-HOLDOUT-1 (Model Lab holdout re-arms on retrain — a Quant Lab
  Law breach; the one real debt).
- Startup schema guard (code ahead of its migration is DOWN, not
  degraded).
- **A legend audit**: the desk legend documents states that nothing
  tests. Render every documented state once. Would have caught the
  v4.36 inverted-limit bug thirteen versions earlier.

---

## 6. THE LAWS THIS SESSION LEARNED (beyond CLAUDE.md)

CLAUDE.md carries the constitution. These are the working rules that
were paid for between v5.00 and v5.17. They are not optional.

**A field that is only ever compared to one value is a boolean, and
the fact it was meant to carry is already gone.** `stage == "ACTIVE"`
was how one SELL position opened both directional cards (v5.19). When
you see that shape, look one function upstream for the `[0]` and the
display string that still has the real value.

**Never infer a fact from silence.** "Quiet long enough, therefore not
expected / retired / delisted" would let a real outage suppress its own
alarm. Refused three times (v5.05, v5.06, v5.13) and it will be asked
again. LIVE, STALE, NEVER_POSTED, UNREACHABLE, NOT_EXPECTED, RETIRED
are distinct facts; the last two come from a human, never from a timer.

**One word carrying two facts is the fault to hunt.** UNKNOWN meant
both "no EMA200 exists" and "an EMA200 exists but its label is
withheld". "news" meant three measurements. STALE meant a broker break,
a dead reporter, a closed market and a young feed. ACTIVE meant "inside
its window" and was read as "levels intact". PASSED meant "passed by"
and read as "pass". Every one of these produced a screen that was
right and looked wrong. When two labels on one page seem to disagree,
find the two questions they answer, then name both. Do not average
them into one word.

**Two right numbers with no anchor are a bug.** "21m old" and "6m since
close" for the same bar. "4.56 ATR" and "4.81 ATR" for the same entry.
A value without its timestamp, its reference price, its timeframe and
its scope is not a fact yet. Label the anchor; do not change the number.

**A threshold is never moved as a side effect.** The freshness gate
measures from a bar's open; the naming fix left it there, because
switching anchors widens every window by a bar — a risk change wearing
a tidy-up's clothes (Iron Rule 7). Same for `symbol_news` (still what
the planner gates on) and `entry_dist_atr` (still what the evidence
records). A naming layer that quietly changes a decision is worse than
the confusion it fixes.

**Recorded evidence is never redefined midway.** `entry_dist_atr` feeds
`LaneObservation` and the fill-rate buckets. Changing what it measures
would split a measured population across two definitions and
contaminate every bucket already stored. Add a labelled second number;
never replace the recorded one.

**Historical is a normal state, not a defect.** A brief is written once
per session block and is historical for most of its life. An outlook
is written once a week. The fix is never "refresh harder"; it is
`written at · value at writing · value now · age`, on every card that
can be old.

**Render the branch; do not grep for the words.** v5.14 shipped a 500
on `/chart?symbol=NVDA` because a renamed variable survived inside a
block that only renders for single stocks, and every test rendered
GOLD. Every conditional template block you add gets a test that
ENTERS it. `grep` proves the words were typed. A render proves they
execute.

**A test written from the same wrong model as the code cannot falsify
it.** v4.36's inverted limit logic shipped with a test asserting the
inverted result. Prefer tests that assert a PROPERTY ("the distance
vocabulary is reachable on both sides") over tests that assert a value
the author already believed.

**When the suite catches you, fix the code, not the test.** Twice in
two versions an old test guarded exactly the property being
strengthened ("calendar-wide" in the narrative; the v5.16 phrasing).
Read what the test protects before touching it. Change a test only
when its assertion encodes a mistake, and say so in its docstring.

**Measured, never invented.** Price at writing is measured from stored
candles, not a new column back-filled with guesses. A feed diagnosis
is decided from the cohort in the candle table, not from a hardcoded
session table. When the platform cannot measure something (a broker's
daily break, whether a limit filled), it says CANNOT SEPARATE or
"a broker fact this distance cannot see" — it does not guess.

**Add keys, never rename or remove them** (append-only, Iron Rule 2).
`label`, `state`, `beyond`, `news`, `age_min` all kept their exact
values; `label_state`, `condition`, `side`, `news_dims`, `bar_clock`
were added beside them.

**Measure "cheap" on the box before believing it.** v5.12's "one cheap
read model" was 2,180 ms on the box — the same aggregation as the Lab.
Cache once for everyone, not once per symbol (`feed_diag._coverage`).

**Secrets never reach chat, logs, templates or commits.** Including the
account registry. Including things that merely look like tokens.

---

## 7. HOW THIS SESSION THINKS — the habits, in order

1. **Findings first, then code.** Trace the paste in code. Say what is
   actually wrong, in one sentence, before proposing anything.
2. **Ask which question each number answers.** Then check whether the
   page says so. Most bugs here are a missing question, not a wrong
   answer.
3. **Refuse the inference.** If the fix would let the system conclude
   something from absence, silence, or a single witness, it is not a
   fix. Name the state as unknown and move on.
4. **Keep the decision where it is.** Display fixes touch display.
   Before pushing, prove nothing gates on what you changed (a test
   that parses the source with `ast` is the house pattern).
5. **Small verified diffs over rewrites.** Anchor-safe edits, one
   organ per change, a test that renders the branch, `pytest -q`,
   commit, push, deploy line, expected output.
6. **Write the CHANGELOG as a story of what was wrong**, not a list of
   what was added. Shyam reads it; the next session reads it. "Why
   this exists" comments belong at the top of every new module.
7. **Put every deferred thing in `docs/OPEN_ITEMS.md` with a
   falsifier** ("finding if: ..."). A watch-item without a falsifier is
   a worry. An item deferred in conversation is an item forgotten.
8. **Report faithfully.** If a test fails, paste the failure. If a
   step was skipped, say so. If the pre-change code also fails a test
   (it happened: `test_p2_ai_lab` depends on another module's seed),
   say that and do not claim it as yours or hide it.
9. **Close with a recap that stands alone.** He may only read the last
   message. Lead with the answer; then what changed; then the deploy
   line; then what is still open. No "let me know if".

---

## 8. PASTE THIS AS THE FIRST MESSAGE OF THE NEW WINDOW

> You are continuing the PLATFORM session for the Brother Bot / Sniper
> System. Repository `sabuj14eu/Sniper-System`, branch
> `claude/brother-bot-trading-platform-58o7gr`, deployed at
> `/srv/brotherbot` on Linux box vmi3221804. Before doing anything,
> read `CLAUDE.md`, then `docs/HANDOFF_PLATFORM_SESSION.md`, then
> `docs/OPEN_ITEMS.md`, then CHANGELOG entries 5.16 and 5.17. You own
> the platform/UI side only; the bot and brain side belongs to another
> session — never touch or propose changes to `/home/shyam/brain-v2` or
> `/home/shyam/brother_sniper_v7`. Never `git checkout` another branch
> on the box. Never activate live stop movement. Never open a PR unless
> asked. I paste commands into a terminal: one paste per step, no
> placeholders, every block starts with `cd /absolute/path &&`, name
> the box above the block, tell me what correct output looks like. Run
> `pytest -q` before every commit. Confirm you have read the three files
> by telling me, in six lines, the current version, the test count, the
> one thing seen and not acted on, and the three laws from the handoff
> you consider most likely to be tested next. Then wait for my first
> task.
