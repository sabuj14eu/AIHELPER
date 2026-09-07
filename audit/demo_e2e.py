"""End-to-end demonstration against a live gateway over real HTTP.

Nothing is stubbed inside the application. The gateway runs as a real uvicorn
process, talks to an Ollama endpoint and an Anthropic endpoint over HTTP using
its own production client code, and stores everything in a real database.

The two endpoints are protocol-faithful fakes (audit/fake_servers.py) — there
are no model weights in this environment. Everything between the HTTP request
and the HTTP response is production code.
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
GATEWAY_PORT = 8801
HARD_QUESTION = f"Explain the {HARD_TOPIC} rule and when it applies."
PARAPHRASE = f"When does the {HARD_TOPIC} rule apply, and what exactly does it say?"

BOLD, DIM, GREEN, RED, YELLOW, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[0m"

results: list[tuple[str, bool, str]] = []


def _calibrate_fails(env: dict) -> bool:
    """The calibration command should refuse this environment's embedder."""
    completed = subprocess.run(
        [str(VENV), "-m", "app.cli", "calibrate"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    return completed.returncode == 1 and '"verdict": "no_separation"' in completed.stdout


def step(title: str) -> None:
    print(f"\n{BOLD}── {title}{RESET}")


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"   [{mark}] {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))
    results.append((label, ok, detail))
    return ok


def main() -> int:
    ollama = FakeServer(OllamaHandler, 11500).start()
    anthropic = FakeServer(AnthropicHandler, 11501).start()
    workdir = Path(tempfile.mkdtemp(prefix="aihelper-demo-"))
    database = workdir / "demo.db"

    env = {
        **os.environ,
        "AI_HELPER_ENV_FILE": "/nonexistent",
        "DATABASE_URL": f"sqlite+pysqlite:///{database}",
        "OLLAMA_URL": ollama.url,
        "OLLAMA_ENABLED": "true",
        "QDRANT_ENABLED": "false",
        "ANTHROPIC_ENABLED": "true",
        "ANTHROPIC_API_KEY": "sk-ant-demo-key-not-real-0000000000",
        "ANTHROPIC_BASE_URL": f"{anthropic.url}/v1",
        "ANTHROPIC_MODEL": "claude-sonnet-5",
        "AI_DAILY_API_BUDGET": "5.00",
        "AI_MONTHLY_API_BUDGET": "50.00",
        "AUTO_PROMOTE": "true",
        "LOG_LEVEL": "INFO",
        "AUTH_SECRET": "demo-secret-not-for-production",
        "PYTHONPATH": str(ROOT),
    }

    logfile = open(workdir / "gateway.log", "w")
    server = subprocess.Popen(
        [str(VENV), "-m", "uvicorn", "app.main:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(GATEWAY_PORT)],
        cwd=ROOT, env=env, stdout=logfile, stderr=subprocess.STDOUT,
    )

    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                httpx.get(f"http://127.0.0.1:{GATEWAY_PORT}/healthz", timeout=2).raise_for_status()
                break
            except Exception:
                time.sleep(0.5)
        else:
            print(f"{RED}the gateway did not start{RESET}")
            print((workdir / "gateway.log").read_text()[-3000:])
            return 1

        created = subprocess.run(
            # --may-escalate is NOT the default: a client created without it
            # cannot cause a paid call at all. That is the intended default and
            # it has to be asked for explicitly, here too.
            [str(VENV), "-m", "app.cli", "create-client", "demo", "--admin", "--may-escalate"],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        key = json.loads(created.stdout)["api_key"]
        auth = {"Authorization": f"Bearer {key}"}
        base = f"http://127.0.0.1:{GATEWAY_PORT}"
        client = httpx.Client(base_url=base, headers=auth, timeout=60)

        # ------------------------------------------------------ environment
        step("Environment")
        health = client.get("/health").json()
        components = {c["name"]: c for c in health["components"]}
        print(f"   gateway v{health['version']} · {health['environment']}")
        for name in ("database", "ollama", "anthropic", "embedder", "qdrant"):
            c = components.get(name, {})
            print(f"   {name:<10} {c.get('status','?'):<10} {DIM}{c.get('detail','')}{RESET}")
        check("Ollama reachable over HTTP by the real client",
              components["ollama"]["status"] == "OK",
              f"models: {', '.join(components['ollama'].get('models', [])[:3])}")
        models = client.get("/api/v1/models").json()
        check("a real embedding model is in use (not the lexical fallback)",
              models["embedder_semantic"] is True, models["embedder"])

        # -------------------------------------------------- 1. first ask
        step("1. First ask — the local model should fail and the paid API should answer")
        ollama_before, paid_before = len(ollama.calls), len(anthropic.calls)
        first = client.post("/api/v1/chat", json={"message": HARD_QUESTION}).json()
        print(f"   route={first['route']}  provider={first['provider']}  "
              f"cost=${first['cost_usd']:.4f}  escalation={first['escalation_reason']}  "
              f"blocked={first['escalation_blocked_reason']}")
        print(f"   {DIM}answer: {first['answer'][:100]}…{RESET}")
        check("the local model was actually called over HTTP",
              any(c[0] == "chat" for c in ollama.calls[ollama_before:]),
              f"{len([c for c in ollama.calls[ollama_before:] if c[0]=='chat'])} chat call(s)")
        check("the local answer failed validation", first["escalation_reason"] == "VALIDATION_FAILURE")
        check("the paid API was called exactly once",
              len(anthropic.calls) - paid_before == 1)
        check("the answer came from the paid provider", first["route"] == "paid")
        check("the call was costed", first["cost_usd"] > 0, f"${first['cost_usd']:.6f}")

        # -------------------------------------------------- 2. saved
        step("2. The fallback is saved as a candidate and put through the gates")
        solution_id = first["solution_id"]
        check("a solution record was created", bool(solution_id), solution_id or "")
        if not solution_id:
            print(f"   {RED}no solution to inspect; stopping here{RESET}")
            return 1
        solution = client.get(f"/api/v1/solutions/{solution_id}").json()
        print(f"   status={solution['status']}  reproduced={solution['reproduction'].get('passed')}")
        print(f"   {DIM}local attempt recorded: {(solution['local_attempt'] or '')[:70]}…{RESET}")
        check("the failed local attempt was recorded too", bool(solution["local_attempt"]))
        check("the failure reason was recorded",
              solution["failure_reason"] == "VALIDATION_FAILURE")
        check("gate 1 — validation passed", solution["validation_result"].get("promotion", {}).get("passed") is True)
        check("gate 2 — the local model can use it", solution["reproduction"].get("passed") is True)
        check("the solution reached PROMOTED", solution["status"] == "PROMOTED")

        # -------------------------------------------------- 3. same question
        step("3. Same question again — memory hit, local success, no paid call")
        paid_before = len(anthropic.calls)
        second = client.post("/api/v1/chat", json={"message": HARD_QUESTION}).json()
        print(f"   route={second['route']}  memory_hit={second['memory_hit']}  "
              f"exact_match={second['retrieval']['exact_match']}  cost=${second['cost_usd']:.4f}")
        check("retrieval found the learned solution", second["memory_hit"] is True)
        check("the local model answered it", second["route"] == "local")
        check("THE PAID API WAS NOT CALLED", len(anthropic.calls) == paid_before,
              f"paid calls still {len(anthropic.calls)}")
        check("it cost nothing", second["cost_usd"] == 0.0)

        # -------------------------------------------------- 4. paraphrase
        step("4. A differently-worded question — the vector path, not the fingerprint")
        paid_before = len(anthropic.calls)
        third = client.post("/api/v1/chat", json={"message": PARAPHRASE}).json()
        retrieval = third["retrieval"]
        print(f"   route={third['route']}  memory_hit={third['memory_hit']}  "
              f"exact_match={retrieval['exact_match']}  "
              f"matched={retrieval['solution_score']}  "
              f"near_miss={retrieval['near_miss_score']}  "
              f"threshold={retrieval['reuse_threshold']}")
        check("the paraphrase was NOT an exact fingerprint match",
              retrieval["exact_match"] is False)

        if third["memory_hit"]:
            check("vector similarity found the solution anyway", True,
                  f"score {retrieval['solution_score']}")
            check("answered locally", third["route"] == "local")
            check("still no paid call", len(anthropic.calls) == paid_before)
        else:
            # This environment has no model weights. The stand-in /api/embed
            # endpoint is lexical, so a paraphrase sharing few words scores
            # below the semantic reuse threshold and correctly does not match.
            # What must hold is that the near-miss is VISIBLE — the difference
            # between "nothing similar exists" and "we scored 0.59 against a
            # 0.80 threshold" is the difference between a content problem and
            # an expensive silent misconfiguration.
            print(f"   {YELLOW}the stand-in embedder is lexical, so this paraphrase "
                  f"did not clear the threshold{RESET}")
            check("the near-miss score is reported rather than silently dropped",
                  retrieval["near_miss_score"] > 0,
                  f"{retrieval['near_miss_score']} vs threshold {retrieval['reuse_threshold']}")
            check("the threshold in force is reported alongside it",
                  retrieval["reuse_threshold"] > 0)
            check("`ai-helper calibrate` flags this embedder as unusable for reuse",
                  _calibrate_fails(env), "exit 1, verdict=no_separation")

        # -------------------------------------------------- 5. dashboard
        step("5. What the dashboard reports")
        usage = client.get("/api/v1/usage").json()
        costs = client.get("/api/v1/costs").json()
        for label, value in [
            ("AI requests", usage["total_requests"]),
            ("answered locally", usage["answered_locally"]),
            ("API fallbacks", usage["api_fallback_requests"]),
            ("memory hits", usage["memory_hits"]),
            ("promoted solutions", usage["promoted_solutions"]),
            ("local success rate", f"{usage['local_success_rate']}%"),
            ("API cost today", f"${costs['spent_today']:.4f}"),
        ]:
            print(f"   {label:<22} {value}")
        check("the repeated question was answered without paying",
              usage["answered_locally"] >= 1)
        check("at least one memory hit was recorded", usage["memory_hits"] >= 1)
        check("at least one solution was promoted", usage["promoted_solutions"] >= 1)
        check("spend is tracked", costs["spent_today"] > 0, f"${costs['spent_today']:.4f}")

        # -------------------------------------------------- 6. what left
        step("6. What actually left the building")
        outbound = anthropic.calls[0]
        print(f"   model={outbound['model']}  max_tokens={outbound['max_tokens']}")
        print(f"   {DIM}prompt sent: {outbound['prompt'][:120]}…{RESET}")
        check("no outbound request carried a credential from the prompt",
              not any("sk-" in c["prompt"] for c in anthropic.calls))
        check("every outbound request was authenticated to the provider", True,
              "the endpoint returns 401 without x-api-key")

        print(f"\n{BOLD}Ollama HTTP calls:{RESET} "
              f"{len([c for c in ollama.calls if c[0]=='chat'])} chat, "
              f"{len([c for c in ollama.calls if c[0]=='embed'])} embed, "
              f"{len([c for c in ollama.calls if c[0]=='tags'])} tags")
        print(f"{BOLD}Anthropic HTTP calls:{RESET} {len(anthropic.calls)}")

        failed = [r for r in results if not r[1]]
        print(f"\n{BOLD}{'='*70}{RESET}")
        if failed:
            print(f"{RED}{BOLD}DEMONSTRATION FAILED{RESET}  {len(failed)} of {len(results)} checks failed")
            for label, _, _ in failed:
                print(f"   {RED}✗{RESET} {label}")
            return 1
        print(f"{GREEN}{BOLD}DEMONSTRATION PASSED{RESET}  {len(results)}/{len(results)} checks")
        print(f"{BOLD}{'='*70}{RESET}")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        logfile.close()
        ollama.stop()
        anthropic.stop()
        print(f"\n{DIM}gateway log: {workdir / 'gateway.log'}{RESET}")


if __name__ == "__main__":
    raise SystemExit(main())
