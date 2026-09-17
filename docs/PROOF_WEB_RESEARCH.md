# Proving web research works — 14 steps

Run these on the box, in order, one line at a time. Every step says what you
should see. **A step that does not produce its expected output is a finding,
not a reason to skip ahead** — the later steps assume the earlier ones.

Nothing here is a PASS from reading code. Until this has been run, the feature
is `AIH-15` in `docs/OPEN_ITEMS.md` and it stays there.

Everything runs on the Contabo box, in `/home/shyam/AIHELPER` (adjust if your
checkout is elsewhere). No paid API is enabled at any point, and nothing is
promoted without you.

---

## Before you start: turn it on

Three things have to be true, and none of them is enough on its own. That is
deliberate — a single switch that grants the internet is a switch someone
flips by accident.

**1. Generate the SearXNG secret and put it in `.env`:**

```
cd /home/shyam/AIHELPER
```
```
echo "SEARXNG_SECRET=$(openssl rand -hex 32)" >> .env
```

**2. Turn web search on and point it at the service:**

```
printf 'WEB_SEARCH_ENABLED=true\nWEB_SEARCH_URL=http://searxng:8080/search\n' >> .env
```

**3. Give the `brother` client the tool by name.** A client with no tool list
inherits every ordinary tool and still gets no internet — inheriting
everything is not the same as choosing this.

```
docker compose exec -T postgres psql -U aihelper -d aihelper -c "UPDATE clients SET allowed_tools = '[\"calculator\",\"date_calculator\",\"document_search\",\"document_list\",\"memory_search\",\"market_news\",\"trading_status\",\"web_search\"]'::json WHERE client_id = 'brother';"
```

Expect: `UPDATE 1`.

---

## Step 1 — bring up SearXNG

```
docker compose up -d searxng
```

Expect: `Container ai-helper-searxng-1  Started`.

## Step 2 — check SearXNG answers JSON, not HTML

This is the setting that is off by SearXNG's default and fails at runtime
looking like our tool is broken.

```
docker compose exec -T ai-helper python -c "import httpx,json; r=httpx.get('http://searxng:8080/search', params={'q':'federal reserve','format':'json'}, timeout=20); print(r.status_code); print(json.dumps(r.json())[:300])"
```

Expect: `200` and a line starting `{"query": "federal reserve", ...`.

- If you see HTML instead, `json` is missing from `search.formats` in
  `deploy/searxng/settings.yml`.
- If you see `429`, the bot limiter is on; `server.limiter` must be `false`.

## Step 3 — rebuild and restart AI Helper with the new code

```
git pull && docker compose up -d --build ai-helper
```

```
docker compose logs --tail=20 ai-helper | grep -i "startup\|trusted_sources"
```

Expect a `startup` line reading `version=1.9.0`, and a `trusted_sources_loaded`
line reading `domains=42 rules=12 min_tier=3`.

## Step 4 — prove a RESTRICTED question never reaches a search box

The promise the whole feature was conditioned on. Do this before anything that
would produce a candidate.

```
docker compose exec -T ai-helper python -c "
from app.core.config import get_settings
from app.database.enums import Classification
from app.runtime import get_runtime
from app.tools.egress import may_use_network
s=get_settings(); r=get_runtime()
for c in ('PUBLIC','INTERNAL','RESTRICTED'):
    d = may_use_network(classification=c, settings=s, client_allowed_tools=['web_search'], client_max_classification=None, registry=r.tools)
    print(c, d.allowed, '-', d.reason)
"
```

Expect `PUBLIC True`, `INTERNAL True`, and **`RESTRICTED False`** with a reason
naming RESTRICTED. If RESTRICTED is True, stop and report it: nothing else in
this document matters.

## Step 5 — take the numbers before

```
docker compose exec -T ai-helper python -m app.cli learning-report
```

Expect JSON. Note `by_origin.self_web`, `promoted` and `total` — these are the
"before" figures, and step 13 compares against them.

## Step 6 — the first research run, on a routed question

```
docker compose exec -T ai-helper python -m app.cli research "what did the FOMC decide at its most recent meeting"
```

Expect JSON, and read these fields in this order:

- `queries` — the **first** one should start `site:federalreserve.gov`. That is
  source routing working: the publisher is asked before the open web.
- `routing_rule` — `fed_policy`.
- `counters.sources_by_tier` — at least one `tier_1`.
- `counters.best_source_tier` — `1`.
- `counters.candidates_created` — `1`.
- `counters.awaiting_approval` — `1`.
- `counters.promoted` — **`0`**. It must be 0. Nothing is adopted without you.
- `relation` — `new` on a first run.

This takes minutes: the local model reads the prompt at ~19.8 tok/s before it
writes anything. That is why the dashboard queues it instead of waiting.

## Step 7 — check the seam between fact and interpretation

```
docker compose exec -T ai-helper python -c "
from app.database.session import session_scope
from app.learning.solution_store import SolutionStore
with session_scope() as s:
    row = SolutionStore(s,'brother').list(limit=1)[0]
    print(row.answer)
"
```

Expect two labelled blocks: `SOURCE FACT (federalreserve.gov):` and
`TRADING INTERPRETATION (reasoning, not a sourced fact):`, plus an `EVIDENCE:`
line. **If they are merged into one paragraph, that is a defect** — the reading
would be inheriting the publisher's citation.

## Step 8 — confirm nothing was promoted

```
docker compose exec -T ai-helper python -m app.cli learning-report
```

Expect `by_origin.self_web` up by 1, `awaiting_approval` up by 1, and
`promoted` **unchanged**.

## Step 9 — run the same question again: the duplicate check

```
docker compose exec -T ai-helper python -m app.cli research "what did the FOMC decide at its most recent meeting"
```

Expect one of two honest outcomes, and both are correct:

- `relation: "duplicate"` with `counters.duplicates_skipped: 1` and
  `candidates_created: 0` — it recognised its own earlier answer. This only
  happens once the first one is **promoted** (step 11), because the check
  compares against promoted knowledge; before that, expect a second candidate.
- a second candidate with `relation: "new"` — correct at this stage.

## Step 10 — a general-web-only question is read, never learned from

```
docker compose exec -T ai-helper python -m app.cli research "what do traders on forums think about gold this week"
```

Expect `ok: false` with a reason starting **`read, not learned:`**, and
`counters.rejected_untrusted_tier: 1`, `candidates_created: 0`. The answer is
still in the output — it was produced and shown, it is simply not something
Brother now believes.

(If a tier 1–3 source happens to rank for that phrasing, this will produce a
candidate instead. That is not a failure; try a phrasing with no official
source behind it.)

## Step 11 — approve it, as a person

Open `https://ai.signalmesh.dev/admin/solutions?origin=self_web`.

Expect the candidate, its origin reading `self_web`, and the button reading
**Confirm** (not Promote). Read the source and the tier before you click. Click
**Confirm**.

Expect the row to move to PROMOTED. This is the only step in this document
that a machine does not do.

## Step 12 — prove it reached the index and comes back

```
docker compose exec -T ai-helper python -m app.cli learning-report
```

Expect `promoted` up by 1, and `retrieval_confirmed` equal to `promoted`.

**`retrieval_confirmed` is the only number here that means Brother can use what
it learned.** PROMOTED is a status; this is the loop closing. If it reads
`NOT RUN`, the vector index could not be read — that is a finding, not a zero.

## Step 13 — ask the question again, and see it answered from memory

```
docker compose exec -T ai-helper python -m app.cli ask "what did the FOMC decide at its most recent meeting"
```

Expect an answer in **seconds, not minutes**, with `[memory ...]` on the
stderr line. That is the cost of the second ask falling to nothing, which is
the entire point of the learning loop.

## Step 14 — confirm no paid API was touched

```
docker compose exec -T ai-helper python -m app.cli learning-report
```

Expect `by_origin.paid: 0`.

```
docker compose exec -T ai-helper python -c "
from app.runtime import get_runtime
print('any paid provider enabled:', get_runtime().providers.any_paid_enabled())
"
```

Expect `False`.

---

## What to paste back

The output of steps 4, 6, 7, 10, 12 and 14. Those six are the claims: the gate
holds, routing reaches the publisher, the seam is visible, tier 4 alone is not
learned from, the loop closes, and it cost nothing.

## How to turn it off again

```
sed -i 's/^WEB_SEARCH_ENABLED=true/WEB_SEARCH_ENABLED=false/' .env && docker compose up -d ai-helper
```

The tool disappears from the registry and the "look this up on the web" link
disappears from the chat. Nothing already learned is affected.
