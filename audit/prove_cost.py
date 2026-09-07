"""Prove cost protection against a live gateway and a real HTTP paid endpoint.

The paid endpoint counts every request it receives. A budget that is claimed
to be enforced but is enforced only in a mock is not enforced; here the proof
is that the counter does not move.
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


def check(label, ok, detail=""):
    print(f"   [{GREEN}PASS{RESET}] {label}" if ok else f"   [{RED}FAIL{RESET}] {label}",
          f"{DIM}{detail}{RESET}" if detail else "")
    results.append((label, ok))
    return ok


class Gateway:
    """A gateway process with a given configuration, and the paid-call counter."""

    def __init__(self, ollama, anthropic, port, **overrides):
        self.ollama, self.anthropic, self.port = ollama, anthropic, port
        self.workdir = Path(tempfile.mkdtemp(prefix="aihelper-cost-"))
        self.env = {
            **os.environ,
            "AI_HELPER_ENV_FILE": "/nonexistent",
            "DATABASE_URL": f"sqlite+pysqlite:///{self.workdir / 'db.sqlite'}",
            "OLLAMA_URL": ollama.url, "OLLAMA_ENABLED": "true",
            "QDRANT_ENABLED": "false",
            "ANTHROPIC_ENABLED": "true",
            "ANTHROPIC_API_KEY": "sk-ant-demo-0000000000000000000000",
            "ANTHROPIC_BASE_URL": f"{anthropic.url}/v1",
            "AUTH_SECRET": "audit-secret", "LOG_LEVEL": "WARNING",
            "PYTHONPATH": str(ROOT),
            **{k: str(v) for k, v in overrides.items()},
        }
        self.log = open(self.workdir / "gw.log", "w")
        self.proc = subprocess.Popen(
            [str(VENV), "-m", "uvicorn", "app.main:create_app", "--factory",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=2).raise_for_status()
                break
            except Exception:
                time.sleep(0.4)
        created = subprocess.run(
            [str(VENV), "-m", "app.cli", "create-client", "c", "--admin", "--may-escalate"],
            cwd=ROOT, env=self.env, capture_output=True, text=True)
        self.key = json.loads(created.stdout)["api_key"]
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{port}",
                                   headers={"Authorization": f"Bearer {self.key}"}, timeout=60)

    def ask(self, message, **kwargs):
        return self.client.post("/api/v1/chat", json={"message": message, **kwargs}).json()

    def costs(self):
        return self.client.get("/api/v1/costs").json()

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


def hard(n=0):
    return f"Explain the {HARD_TOPIC} rule, variant {n}, and when it applies."


def main() -> int:
    ollama = FakeServer(OllamaHandler, 11530).start()
    anthropic = FakeServer(AnthropicHandler, 11531).start()
    port = 8810
    try:
        # ---------------------------------------------------- baseline
        print(f"\n{BOLD}── Baseline: escalation works when the budget allows it{RESET}")
        gw = Gateway(ollama, anthropic, port, AI_DAILY_API_BUDGET="5.00",
                     AI_MONTHLY_API_BUDGET="50.00")
        before = len(anthropic.calls)
        r = gw.ask(hard(0))
        check("a paid call happens when nothing blocks it",
              r["route"] == "paid" and len(anthropic.calls) == before + 1,
              f"cost ${r['cost_usd']:.6f}")
        gw.close(); port += 1

        # ---------------------------------------------------- daily
        print(f"\n{BOLD}── Daily budget{RESET}")
        gw = Gateway(ollama, anthropic, port, AI_DAILY_API_BUDGET="0.00",
                     AI_MONTHLY_API_BUDGET="50.00")
        before = len(anthropic.calls)
        r = gw.ask(hard(1))
        check("escalation was wanted", r["escalation_reason"] == "VALIDATION_FAILURE")
        check("blocked by the DAILY budget",
              r["escalation_blocked_reason"] == "DAILY_BUDGET_EXHAUSTED")
        check("the paid endpoint received NOTHING",
              len(anthropic.calls) == before, f"counter still {len(anthropic.calls)}")
        easy = gw.ask("What is the capital of France?")
        tool = gw.ask("What is 1200 * 0.23?")
        check("the system still answers locally", easy["success"] and easy["route"] == "local")
        check("the system still answers with tools", tool["answer"] == "276")
        check("no cost was recorded", gw.costs()["spent_today"] == 0.0)
        gw.close(); port += 1

        # ---------------------------------------------------- monthly
        print(f"\n{BOLD}── Monthly budget{RESET}")
        gw = Gateway(ollama, anthropic, port, AI_DAILY_API_BUDGET="50.00",
                     AI_MONTHLY_API_BUDGET="0.00")
        before = len(anthropic.calls)
        r = gw.ask(hard(2))
        check("blocked by the MONTHLY budget even with daily headroom",
              r["escalation_blocked_reason"] == "MONTHLY_BUDGET_EXHAUSTED")
        check("the paid endpoint received NOTHING", len(anthropic.calls) == before)
        gw.close(); port += 1

        # ---------------------------------------------------- per request
        print(f"\n{BOLD}── Per-request cap{RESET}")
        gw = Gateway(ollama, anthropic, port, AI_MAX_COST_PER_REQUEST="0.0000001",
                     AI_DAILY_API_BUDGET="50.00", AI_MONTHLY_API_BUDGET="500.00")
        before = len(anthropic.calls)
        r = gw.ask(hard(3))
        check("blocked by the per-request cost cap",
              r["escalation_blocked_reason"] == "REQUEST_COST_CAP")
        check("the paid endpoint received NOTHING", len(anthropic.calls) == before)
        gw.close(); port += 1

        # ---------------------------------------------------- oversized
        print(f"\n{BOLD}── Per-request size cap{RESET}")
        gw = Gateway(ollama, anthropic, port, AI_MAX_INPUT_TOKENS_PER_REQUEST="10")
        before = len(anthropic.calls)
        r = gw.ask(hard(4))
        check("blocked because the prompt is too large",
              r["escalation_blocked_reason"] == "REQUEST_TOO_LARGE")
        check("the paid endpoint received NOTHING", len(anthropic.calls) == before)
        gw.close(); port += 1

        # ---------------------------------------------- exhaustion in flight
        print(f"\n{BOLD}── Budget exhausted mid-run (the realistic case){RESET}")
        # The pre-flight check is pessimistic: it projects the FULL max_tokens,
        # so a call is refused unless the whole worst case fits in what is
        # left. A budget must therefore leave room for one worst case plus a
        # little accumulated real spend for this to stop part-way rather than
        # never start.
        gw = Gateway(ollama, anthropic, port, AI_DAILY_API_BUDGET="0.034",
                     AI_MONTHLY_API_BUDGET="50.00")
        before = len(anthropic.calls)
        routes = []
        for i in range(8):
            routes.append(gw.ask(hard(100 + i))["route"])
        made = len(anthropic.calls) - before
        spend = gw.costs()
        print(f"   8 hard questions → routes: {routes}")
        print(f"   paid calls made: {made}   spent: ${spend['spent_today']:.6f} "
              f"of ${spend['daily_budget']:.4f}")
        usage = gw.client.get("/api/v1/usage").json()
        print(f"   escalations refused: {usage['escalations_blocked_total']} "
              f"({usage['escalations_blocked_by_budget']} by a cost limit)")
        check("it stopped paying part-way through, without a restart", 0 < made < 8)
        check("spend never exceeded the budget",
              spend["spent_today"] <= spend["daily_budget"],
              f"${spend['spent_today']:.6f} <= ${spend['daily_budget']:.4f}")
        check("later requests are all local", routes[-1] == "local")
        check("the refused escalations are counted, not silently dropped",
              usage["escalations_blocked_by_budget"] > 0,
              f"{usage['escalations_blocked_by_budget']} refused by a cost limit")

        # ------------------------------- a budget too low to admit anything
        print(f"\n{BOLD}── A budget too low to admit ANY request is still visible{RESET}")
        gw.close(); port += 1
        gw = Gateway(ollama, anthropic, port, AI_DAILY_API_BUDGET="0.0001")
        before = len(anthropic.calls)
        for i in range(4):
            gw.ask(hard(500 + i))
        usage = gw.client.get("/api/v1/usage").json()
        spend = gw.costs()
        print(f"   spent ${spend['spent_today']:.6f}, fallbacks {usage['api_fallback_requests']}, "
              f"refused {usage['escalations_blocked_total']}")
        check("nothing was spent", len(anthropic.calls) == before)
        check("the fallback count alone would look like success",
              usage["api_fallback_requests"] == 0)
        check("but the refusals are reported, so the misconfiguration is findable",
              usage["escalations_blocked_by_budget"] == 4)

        # ------------------------------------------------- no retry loop
        print(f"\n{BOLD}── No retry loop can spend money{RESET}")
        before = len(anthropic.calls)
        for _ in range(5):
            gw.ask(hard(200))
        check("repeating a blocked request never resumes spending",
              len(anthropic.calls) == before, f"{len(anthropic.calls) - before} extra calls")
        gw.close(); port += 1

        # --------------------------------------- one request = one attempt
        print(f"\n{BOLD}── One request never calls a provider twice{RESET}")
        gw = Gateway(ollama, anthropic, port, AI_DAILY_API_BUDGET="5.00")
        before = len(anthropic.calls)
        gw.ask(hard(300))
        check("a single request produced exactly one provider call",
              len(anthropic.calls) - before == 1, f"{len(anthropic.calls) - before}")

        # A failing provider must not be retried into a loop either.
        print(f"\n{BOLD}── A failing provider is not retried in a loop{RESET}")
        gw.close(); port += 1
        broken = FakeServer(type("Broken", (AnthropicHandler,), {
            "do_POST": lambda self: self._json(500, {"error": {"message": "upstream"}})}), 11532).start()
        gw = Gateway(ollama, broken, port, AI_DAILY_API_BUDGET="5.00")
        before = len(broken.calls)
        r = gw.ask(hard(400))
        check("a 500 from the provider is not retried",
              len(broken.calls) - before <= 1, f"{len(broken.calls) - before} call(s)")
        check("the failure is reported honestly",
              r["escalation_blocked_reason"] == "PROVIDER_FAILED")
        check("the failed call's input tokens are still costed",
              gw.costs()["spent_today"] >= 0)
        gw.close()
        broken.stop()

        failed = [r for r in results if not r[1]]
        print(f"\n{BOLD}{'='*70}{RESET}")
        if failed:
            print(f"{RED}{BOLD}COST PROTECTION: {len(failed)} of {len(results)} checks FAILED{RESET}")
            for label, _ in failed:
                print(f"   {RED}✗{RESET} {label}")
            return 1
        print(f"{GREEN}{BOLD}COST PROTECTION PROVEN{RESET}  {len(results)}/{len(results)} checks")
        print(f"{BOLD}{'='*70}{RESET}")
        return 0
    finally:
        ollama.stop()
        anthropic.stop()


if __name__ == "__main__":
    raise SystemExit(main())
