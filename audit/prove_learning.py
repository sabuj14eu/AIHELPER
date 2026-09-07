"""The learning system: an API answer is never automatically trusted.

    API result → Candidate → Validation → Promotion → Reusable knowledge

Each arrow is attacked: can a bad answer skip a gate?
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from fake_servers import HARD_TOPIC, AnthropicHandler, FakeServer, OllamaHandler  # noqa: E402

ROOT = Path(__file__).parent.parent
VENV = ROOT / ".venv" / "bin" / "python"
BOLD, DIM, GREEN, RED, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m"
results = []


def section(t): print(f"\n{BOLD}── {t}{RESET}")


def check(label, ok, detail=""):
    print(f"   [{GREEN}PASS{RESET}] {label}" if ok else f"   [{RED}FAIL{RESET}] {label}",
          f"{DIM}{detail}{RESET}" if detail else "")
    results.append((label, ok))
    return ok


class Refusing(AnthropicHandler):
    """A paid provider that answers with a refusal."""
    def do_POST(self):
        body = self._read()
        self.server.calls.append({"model": body.get("model"), "prompt": "", "system": "",
                                  "max_tokens": body.get("max_tokens")})
        self._json(200, {"id": "m", "type": "message", "role": "assistant",
                         "model": "claude-sonnet-5",
                         "content": [{"type": "text", "text": "I cannot help with that request."}],
                         "stop_reason": "end_turn",
                         "usage": {"input_tokens": 10, "output_tokens": 8}})


class ActionClaiming(AnthropicHandler):
    """A paid provider that claims it performed an action."""
    def do_POST(self):
        body = self._read()
        self.server.calls.append({"model": body.get("model"), "prompt": "", "system": "",
                                  "max_tokens": body.get("max_tokens")})
        self._json(200, {"id": "m", "type": "message", "role": "assistant",
                         "model": "claude-sonnet-5",
                         "content": [{"type": "text",
                                      "text": "I have deleted the invoices and emailed the report."}],
                         "stop_reason": "end_turn",
                         "usage": {"input_tokens": 10, "output_tokens": 12}})


def gateway(ollama, paid, port, workdir, **overrides):
    env = {**os.environ, "AI_HELPER_ENV_FILE": "/nonexistent",
           "DATABASE_URL": f"sqlite+pysqlite:///{workdir / f'db{port}.sqlite'}",
           "OLLAMA_URL": ollama.url, "OLLAMA_ENABLED": "true", "QDRANT_ENABLED": "false",
           "ANTHROPIC_ENABLED": "true", "ANTHROPIC_API_KEY": "sk-ant-x-00000000000000000000",
           "ANTHROPIC_BASE_URL": f"{paid.url}/v1",
           "AI_DAILY_API_BUDGET": "5.00", "AUTH_SECRET": "audit-secret",
           "LOG_LEVEL": "WARNING", "RATE_LIMIT_BURST": "500", "RATE_LIMIT_PER_MINUTE": "5000",
           "MEMORY_SIMILARITY_THRESHOLD": "0.25", "SOLUTION_REUSE_THRESHOLD": "0.45",
           "PYTHONPATH": str(ROOT), **{k: str(v) for k, v in overrides.items()}}
    log = open(workdir / f"gw{port}.log", "w")
    proc = subprocess.Popen([str(VENV), "-m", "uvicorn", "app.main:create_app", "--factory",
                             "--host", "127.0.0.1", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=2).raise_for_status(); break
        except Exception:
            time.sleep(0.4)
    key = json.loads(subprocess.run(
        [str(VENV), "-m", "app.cli", "create-client", "c", "--admin", "--may-escalate"],
        cwd=ROOT, env=env, capture_output=True, text=True).stdout)["api_key"]
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}",
                          headers={"Authorization": f"Bearer {key}"}, timeout=60)
    return proc, log, client


def stop(proc, log):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


def main() -> int:
    ollama = FakeServer(OllamaHandler, 11580).start()
    good = FakeServer(AnthropicHandler, 11581).start()
    refusing = FakeServer(Refusing, 11582).start()
    claiming = FakeServer(ActionClaiming, 11583).start()
    workdir = Path(tempfile.mkdtemp(prefix="aihelper-learn-"))
    hard = f"Explain the {HARD_TOPIC} rule and when it applies."
    procs = []
    try:
        # ---------------------------------------- the pipeline in order
        section("An API answer enters as a CANDIDATE, never as knowledge")
        p, lg, c = gateway(ollama, good, 8850, workdir, AUTO_PROMOTE="false")
        procs.append((p, lg))
        r = c.post("/api/v1/chat", json={"message": hard}).json()
        sol = c.get(f"/api/v1/solutions/{r['solution_id']}").json()
        check("the paid answer was stored", bool(r["solution_id"]))
        check("its status is CANDIDATE, not knowledge", sol["status"] == "CANDIDATE")
        check("it was NOT promoted automatically", sol["promoted_at"] is None)

        before = len(good.calls)
        second = c.post("/api/v1/chat", json={"message": hard}).json()
        check("a CANDIDATE is not offered back to the model",
              second["memory_hit"] is False and second["route"] == "paid")
        check("so the same question escalates again until a human promotes it",
              len(good.calls) == before + 1)

        section("Promotion is a separate, explicit act")
        outcome = c.post(f"/api/v1/solutions/{r['solution_id']}/promote").json()
        check("promotion runs both gates", outcome["status"] == "PROMOTED",
              f"reproduction={outcome['reproduction'].get('passed')}")
        third = c.post("/api/v1/chat", json={"message": hard}).json()
        check("only now is it reused", third["memory_hit"] and third["route"] == "local")
        stop(*procs.pop())

        # ------------------------------------------- gate 1: validation
        section("Gate 1 — an answer that fails validation is never stored")
        p, lg, c = gateway(ollama, refusing, 8851, workdir, AUTO_PROMOTE="true")
        procs.append((p, lg))
        r = c.post("/api/v1/chat", json={"message": hard}).json()
        check("the provider was called", len(refusing.calls) > 0)
        check("its refusal is not treated as an answer", r["success"] is False)
        check("nothing was stored as a candidate", r["solution_id"] is None)
        check("the reason is stated", any("failed validation" in n for n in r["notes"]),
              "; ".join(r["notes"])[:70])
        check("the solution store is empty", c.get("/api/v1/solutions").json() == [])
        stop(*procs.pop())

        section("Gate 1 — an answer claiming an action is never stored")
        p, lg, c = gateway(ollama, claiming, 8852, workdir, AUTO_PROMOTE="true")
        procs.append((p, lg))
        r = c.post("/api/v1/chat", json={"message": hard}).json()
        check("the action claim is caught", r["success"] is False)
        check("it is not stored", r["solution_id"] is None)
        check("the safety finding names it",
              any("action" in str(f).lower() for f in
                  r["validation"].get("safety", {}).get("findings", [])),
              str(r["validation"].get("safety", {}).get("findings", ""))[:70])
        stop(*procs.pop())

        # ----------------------------------------- gate 2: reproduction
        section("Gate 2 — an answer the local model cannot use is rejected")
        # A local model that always fails, even with the solution in front of it.
        class Useless(OllamaHandler):
            def _chat(self, body):
                self.server.calls.append(("chat", body.get("model")))
                self._json(200, {"model": body.get("model"), "done": True, "done_reason": "stop",
                                 "message": {"role": "assistant",
                                             "content": "INSUFFICIENT_CONTEXT — still no idea."},
                                 "prompt_eval_count": 5, "eval_count": 5})
        useless = FakeServer(Useless, 11584).start()
        p, lg, c = gateway(useless, good, 8853, workdir, AUTO_PROMOTE="true")
        procs.append((p, lg))
        r = c.post("/api/v1/chat", json={"message": hard}).json()
        sol = c.get(f"/api/v1/solutions/{r['solution_id']}").json()
        check("the candidate was created", sol["id"] == r["solution_id"])
        check("gate 1 passed but gate 2 did not", sol["status"] == "REJECTED",
              f"status={sol['status']}")
        check("the rejection says why",
              "even with this solution as context" in (sol["status_reason"] or ""),
              (sol["status_reason"] or "")[:70])
        check("a REJECTED solution is never retrieved",
              c.post("/api/v1/chat", json={"message": hard}).json()["memory_hit"] is False)
        stop(*procs.pop())
        useless.stop()

        # -------------------------------------------- rejection is real
        section("A human rejection removes it from circulation")
        p, lg, c = gateway(ollama, good, 8854, workdir, AUTO_PROMOTE="true")
        procs.append((p, lg))
        r = c.post("/api/v1/chat", json={"message": hard}).json()
        check("auto-promotion reached PROMOTED",
              c.get(f"/api/v1/solutions/{r['solution_id']}").json()["status"] == "PROMOTED")
        check("it is reused", c.post("/api/v1/chat", json={"message": hard}).json()["memory_hit"])
        c.post(f"/api/v1/solutions/{r['solution_id']}/reject",
               params={"reason": "a reviewer found it wrong"})
        after = c.post("/api/v1/chat", json={"message": hard}).json()
        check("after rejection it is no longer retrieved", after["memory_hit"] is False)
        check("and the question escalates again rather than serving a bad answer",
              after["route"] == "paid")

        section("The whole lifecycle is visible and auditable")
        counts = c.get("/api/v1/solutions/counts").json()
        check("every status is reported",
              set(counts) == {"CANDIDATE", "VALIDATED", "PROMOTED", "REJECTED", "EXPIRED"},
              str(counts))
        events = c.get("/api/v1/admin/audit", params={"limit": 200}).json()
        actions = {e["action"] for e in events}
        for action in ("learning.solution_captured", "learning.solution_validated",
                       "learning.solution_promoted", "learning.solution_rejected"):
            check(f"audited: {action}", action in actions)
        fallbacks = c.get("/api/v1/usage/fallbacks").json()
        check("the fallback report shows why local failed and what happened next",
              fallbacks and fallbacks[0]["failure_reason"] and fallbacks[0]["status"],
              f"{fallbacks[0]['failure_reason']} → {fallbacks[0]['status']}" if fallbacks else "")
        stop(*procs.pop())

        failed = [r for r in results if not r[1]]
        print(f"\n{BOLD}{'='*70}{RESET}")
        if failed:
            print(f"{RED}{BOLD}{len(failed)} of {len(results)} checks FAILED{RESET}")
            for label, _ in failed:
                print(f"   {RED}✗{RESET} {label}")
            return 1
        print(f"{GREEN}{BOLD}LEARNING SYSTEM PROVEN{RESET}  {len(results)}/{len(results)} checks")
        print(f"{BOLD}{'='*70}{RESET}")
        return 0
    finally:
        for pr in procs:
            stop(*pr)
        for srv in (ollama, good, refusing, claiming):
            srv.stop()


if __name__ == "__main__":
    raise SystemExit(main())
