"""Learning, reuse and privacy against a REAL local model and REAL embedder.

Drives a running gateway (the Docker stack) whose local model and embedder
are real Ollama models and whose *paid* provider is the protocol-faithful
Anthropic stand-in from audit/fake_servers.py, started here on port 11601
and reached from the container as host.docker.internal:11601. The stand-in
answers one hard question with a fixed, correct paragraph; everything else —
routing, validation, capture, the reproduction gate run by the real model,
promotion, indexing with the real embedder, retrieval, the privacy gate and
the audit trail — is production code against real services.

Proves, with the gateway's own responses and the stand-in's call log:

  learning     hard question → local fails → paid fallback → validated →
               CANDIDATE → reproduced by the REAL model → PROMOTED
  reuse        a reworded question → memory hit → answered locally → paid = 0
               (and the literal repeat → exact fingerprint match)
  privacy      RESTRICTED memory, a CONFIDENTIAL document and a client whose
               data is CONFIDENTIAL by default never reach the stand-in, the
               refusal is audited; an INTERNAL control still escalates

Usage (gateway started with ANTHROPIC_ENABLED=true, ANTHROPIC_BASE_URL=
http://host.docker.internal:11601/v1, AUTO_PROMOTE=true):

    AI_HELPER_URL=http://127.0.0.1:8000 AI_HELPER_ADMIN_KEY=ahk_... \
        .venv/bin/python audit/real_model_learning.py [--out DIR]

Exits non-zero on any FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from fake_servers import AnthropicHandler, FakeServer  # noqa: E402

# The stand-in's fixed answer, phrased for the question actually asked below so
# that the learned solution genuinely answers its paraphrase. (The generic
# PAID_ANSWER in fake_servers.py never mentions the company; handed that text
# for "our company's rule", the real model correctly said the context did not
# cover it — which is the discipline the reuse path relies on, working.)
COMPANY_ANSWER = (
    "Our company's health contribution look-back rule: under the flat tax the health "
    "contribution for a month is 4.9% of the income of the month before it. The "
    "contribution year runs from 1 February to 31 January, so January is settled on the "
    "previous year's figures. The rule applies to every month in which the company is "
    "taxed under the flat tax."
)


class CompanyHandler(AnthropicHandler):
    def do_POST(self):  # noqa: N802
        body = self._read()
        if not self.path.endswith("/messages"):
            self._json(404, {"error": "not found"})
            return
        turns = body.get("messages", [])
        prompt = "\n".join(m.get("content", "") for m in turns)
        self.server.calls.append({"model": body.get("model"), "prompt": prompt, "system": body.get("system", ""), "max_tokens": body.get("max_tokens")})
        self._json(200, {"id": f"msg_{len(self.server.calls):06d}", "type": "message", "role": "assistant",
                         "model": body.get("model", "claude-sonnet-5"),
                         "content": [{"type": "text", "text": COMPANY_ANSWER}], "stop_reason": "end_turn",
                         "usage": {"input_tokens": max(1, len(prompt) // 4), "output_tokens": max(1, len(COMPANY_ANSWER) // 4)}})

# On the GENERAL path llama3.2:3b refuses this 3/3 (it has no such rule), so the
# fallback is triggered by the model itself, not by a task type that forces it.
HARD = "Explain our company's health contribution look-back rule and when it applies."
PARAPHRASE = "When does our company's health contribution look-back rule apply, and what does it say?"
RESTRICTED_NOTE = "The margin on the Nowak contract is forty-two percent."
CONFIDENTIAL_DOC = (
    "Supply contract summary. The buyer pays a confidential rebate of nineteen percent "
    "to the seller under the Zieliński supply contract, settled quarterly."
)
INTERNAL_NOTE = "The Kowalczyk contract is background reading only; nothing sensitive in it."

BOLD, DIM, GREEN, RED, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m"
results: list[tuple[str, bool, str]] = []
record: dict = {"steps": []}


def section(title: str) -> None:
    print(f"\n{BOLD}── {title}{RESET}")


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"   [{GREEN}PASS{RESET}] {label}" if ok else f"   [{RED}FAIL{RESET}] {label}",
          f"{DIM}{detail}{RESET}" if detail else "")
    results.append((label, ok, detail))
    return ok


def keep(name: str, payload: dict) -> dict:
    slim = {k: v for k, v in payload.items() if k not in ("validation", "retrieval")}
    slim["validation"] = {k: payload.get("validation", {}).get(k) for k in ("passed", "confidence", "vetoes")}
    slim["retrieval"] = payload.get("retrieval")
    record["steps"].append({"name": name, **slim})
    return payload


def make_client(admin: httpx.Client, base: str, client_id: str, **params) -> httpx.Client:
    r = admin.post("/api/v1/admin/clients", params={"client_id": client_id, **params})
    r.raise_for_status()
    key = r.json()["api_key"]
    return httpx.Client(base_url=base, headers={"Authorization": f"Bearer {key}"}, timeout=300)


def sent_to_stand_in(stand_in: FakeServer) -> str:
    return "\n".join(c["prompt"] + "\n" + c.get("system", "") for c in stand_in.calls)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.environ.get("EVAL_OUT", "audit/results"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = os.environ.get("AI_HELPER_URL", "http://127.0.0.1:8000")
    admin_key = os.environ["AI_HELPER_ADMIN_KEY"]
    admin = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {admin_key}"}, timeout=120)

    stand_in = FakeServer(CompanyHandler, 11601, bind="0.0.0.0").start()
    stamp = str(int(time.time()))
    record["health"] = admin.get("/health").json()
    record["models"] = admin.get("/api/v1/models").json()
    check("the gateway reports a real, semantic embedder",
          any(c["name"] == "embedder" and c["status"] == "OK" for c in record["health"]["components"]),
          str([(c["name"], c["status"], c.get("detail")) for c in record["health"]["components"] if c["name"] in ("ollama", "embedder", "anthropic")]))
    check("the anthropic provider is enabled (pointing at the stand-in)",
          any(c["name"] == "anthropic" and c["status"] != "DISABLED" for c in record["health"]["components"]))

    # ------------------------------------------------------------ learning
    section("LEARNING: hard question → local failure → paid fallback → candidate → promotion")
    learner = make_client(admin, base, f"learn-{stamp}", may_escalate="true")
    calls_before = len(stand_in.calls)
    first = keep("first_ask", learner.post("/api/v1/chat", json={"message": HARD, "store_conversation": False}).json())
    check("the local model was tried first and did not pass (fallback had a reason)",
          bool(first.get("escalation_reason")), f"reason={first.get('escalation_reason')} local_conf_before={first.get('validation', {}).get('confidence')}")
    check("the answer came from the paid provider", first.get("route") == "paid" and first.get("provider") == "anthropic", f"route={first.get('route')} provider={first.get('provider')}")
    check("the paid call was billed", (first.get("cost_usd") or 0) > 0, f"cost={first.get('cost_usd')}")
    check("the stand-in received exactly one call", len(stand_in.calls) == calls_before + 1)
    check("the paid answer passed validation", first.get("validation", {}).get("passed") is True, f"conf={first.get('confidence')}")
    check("it was captured as a solution", bool(first.get("solution_id")), first.get("solution_id") or "")
    solution = {}
    if first.get("solution_id"):
        solution = learner.get(f"/api/v1/solutions/{first['solution_id']}").json()
        record["solution"] = {k: solution.get(k) for k in ("id", "status", "status_reason", "reproduction", "question", "task_type")}
        repro = solution.get("reproduction") or {}
        check("the reproduction gate was run by the REAL local model", repro.get("attempted") is True and str(repro.get("model", "")).startswith("llama"), json.dumps(repro))
        check("the solution reached PROMOTED", solution.get("status") == "PROMOTED", f"status={solution.get('status')} reason={solution.get('status_reason')}")

    # -------------------------------------------------------------- reuse
    section("REUSE: a reworded question is answered locally from the learned solution")
    calls_before = len(stand_in.calls)
    second = keep("paraphrase_ask", learner.post("/api/v1/chat", json={"message": PARAPHRASE, "store_conversation": False}).json())
    check("retrieval found the learned solution for the paraphrase (memory hit)", second.get("memory_hit") is True, json.dumps(second.get("retrieval")))
    check("the same solution was reused", second.get("solution_id") == first.get("solution_id"), f"{second.get('solution_id')} vs {first.get('solution_id')}")
    check("the answer was produced locally by the real model", second.get("route") == "local" and second.get("provider") == "ollama" and str(second.get("model", "")).startswith("llama"), f"route={second.get('route')} model={second.get('model')}")
    check("it passed validation", second.get("success") is True and second.get("validation", {}).get("passed") is True, f"conf={second.get('confidence')} vetoes={second.get('validation', {}).get('vetoes')}")
    check("no paid call was made and nothing was billed", len(stand_in.calls) == calls_before and (second.get("cost_usd") or 0) == 0)
    check("the answer carries the learned substance", "february" in (second.get("answer") or "").lower() or "4.9" in (second.get("answer") or ""), (second.get("answer") or "")[:160])

    third = keep("exact_repeat", learner.post("/api/v1/chat", json={"message": HARD, "store_conversation": False}).json())
    check("the literal repeat is an exact fingerprint match, local and free",
          third.get("retrieval", {}).get("exact_match") is True and third.get("route") == "local" and (third.get("cost_usd") or 0) == 0,
          f"exact={third.get('retrieval', {}).get('exact_match')} route={third.get('route')}")
    usage = learner.get("/api/v1/usage").json()
    record["usage"] = usage
    check("usage shows one fallback and at least two memory hits for this client",
          usage.get("api_fallback_requests", 0) >= 1 and usage.get("memory_hits", 0) >= 2,
          json.dumps({k: usage.get(k) for k in ("total_requests", "local_requests", "api_fallback_requests", "memory_hits", "promoted_solutions", "estimated_money_saved_usd")}))

    # ------------------------------------------------------------ privacy
    section("PRIVACY: what retrieval puts in front of the model may not leave")
    priv = make_client(admin, base, f"privacy-{stamp}", may_escalate="true")
    priv.post("/api/v1/memory", json={"content": RESTRICTED_NOTE, "source": "audit", "confidence": 0.9, "sensitivity": "RESTRICTED"}).raise_for_status()
    doc = priv.post("/api/v1/documents", files={"file": ("contract.txt", CONFIDENTIAL_DOC.encode(), "text/plain")}, data={"classification": "CONFIDENTIAL", "title": "Supply contract"})
    doc.raise_for_status()
    check("the CONFIDENTIAL document is indexed", doc.json().get("status") == "ready", json.dumps({k: doc.json().get(k) for k in ("status", "chunk_count", "classification")}))

    def probe(label: str, client: httpx.Client, questions: list[str], expect_class: str, secret: str) -> None:
        exercised = False
        for q in questions:
            calls_before = len(stand_in.calls)
            r = keep(label, client.post("/api/v1/chat", json={"message": q, "task_type": "research", "store_conversation": False}).json())
            leaked = secret in sent_to_stand_in(stand_in)
            check(f"{label}: '{secret}' never reached the stand-in", not leaked)
            if r.get("escalation_reason"):
                exercised = True
                check(f"{label}: the request was judged {expect_class} once the context was retrieved", r.get("classification") == expect_class, f"classification={r.get('classification')} notes={r.get('notes')}")
                check(f"{label}: escalation was refused on classification", r.get("escalation_blocked_reason") == "CLASSIFICATION_BLOCKED", f"blocked={r.get('escalation_blocked_reason')}")
                check(f"{label}: the stand-in was not called", len(stand_in.calls) == calls_before)
                break
            print(f"      {DIM}local answered without wanting to escalate ({r.get('confidence')}); trying the next probe{RESET}")
        check(f"{label}: the external gate was actually exercised", exercised)

    probe("RESTRICTED memory", priv,
          ["Who negotiated the Nowak contract margin and when was it signed?",
           "Which lawyer approved the Nowak contract margin and on what date?"],
          "RESTRICTED", "forty-two")
    probe("CONFIDENTIAL document", priv,
          ["What penalty applies if the rebate under the Zieliński supply contract is paid late?",
           "Who signed the Zieliński supply contract rebate clause and when does it expire?"],
          "CONFIDENTIAL", "nineteen percent")

    # Categorically sensitive client data: the classification is the default,
    # not something a regex has to notice.
    conf = make_client(admin, base, f"confidential-{stamp}", may_escalate="true", default_classification="CONFIDENTIAL")
    calls_before = len(stand_in.calls)
    r = keep("confidential_by_default", conf.post("/api/v1/chat", json={"message": "What are the current financing options for a second delivery van for the shop?", "task_type": "research", "store_conversation": False}).json())
    check("a client whose data is CONFIDENTIAL by default is classified so without any pattern", r.get("classification") == "CONFIDENTIAL", f"classification={r.get('classification')}")
    check("…and its request was not sent out", len(stand_in.calls) == calls_before and r.get("route") != "paid", f"route={r.get('route')} blocked={r.get('escalation_blocked_reason')}")

    # Control: INTERNAL context still escalates — the gate is not a blanket block.
    ctrl = make_client(admin, base, f"control-{stamp}", may_escalate="true")
    ctrl.post("/api/v1/memory", json={"content": INTERNAL_NOTE, "source": "audit", "confidence": 0.9, "sensitivity": "INTERNAL"}).raise_for_status()
    calls_before = len(stand_in.calls)
    r = keep("internal_control", ctrl.post("/api/v1/chat", json={"message": "Who negotiated the Kowalczyk contract and when was it signed?", "task_type": "research", "store_conversation": False}).json())
    check("INTERNAL context still escalates (the gate is not a blanket block)", len(stand_in.calls) == calls_before + 1 and r.get("route") == "paid", f"route={r.get('route')} class={r.get('classification')} blocked={r.get('escalation_blocked_reason')}")

    audit_rows = admin.get("/api/v1/admin/audit", params={"action": "privacy.escalation_blocked", "limit": 50}).json()
    rows = audit_rows if isinstance(audit_rows, list) else audit_rows.get("events", audit_rows.get("items", []))
    ours = [e for e in rows if str(e.get("actor", "")).endswith(stamp)]
    check("every privacy refusal left an audit row", len(ours) >= 3, f"{len(ours)} rows for this run")
    record["audit_privacy_rows"] = [{k: e.get(k) for k in ("actor", "action", "result", "detail")} for e in ours][:6]

    # ------------------------------------------------------------- verdict
    failed = [r for r in results if not r[1]]
    record["checks"] = [{"label": lbl, "ok": ok, "detail": d} for lbl, ok, d in results]
    record["summary"] = {"checks": len(results), "passed": len(results) - len(failed), "failed": len(failed), "stand_in_calls": len(stand_in.calls)}
    (out / "real_model_learning.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    print(f"\n{BOLD}{'LEARNING, REUSE AND PRIVACY PROVEN' if not failed else 'FAILED'}: {len(results) - len(failed)}/{len(results)}{RESET}")
    stand_in.stop()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
