"""Container restart persistence, against the real Docker stack.

Real image, real containers, real PostgreSQL, real Qdrant, real named volumes.
The two model endpoints are stand-ins running on the host — this gate is about
whether data survives a restart, not about model quality.

The test that matters: create data, `docker compose down`, `docker compose up`,
and check that nothing was silently lost.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from fake_servers import HARD_TOPIC, AnthropicHandler, FakeServer, OllamaHandler  # noqa: E402

ROOT = Path(__file__).parent.parent
BOLD, DIM, GREEN, RED, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m"
BASE = "http://localhost:8000"
results = []


def section(t): print(f"\n{BOLD}── {t}{RESET}")


def check(label, ok, detail=""):
    print(f"   [{GREEN}PASS{RESET}] {label}" if ok else f"   [{RED}FAIL{RESET}] {label}",
          f"{DIM}{detail}{RESET}" if detail else "")
    results.append((label, ok))
    return ok


def compose(*args, capture=True):
    return subprocess.run(["docker", "compose", *args], cwd=ROOT,
                          capture_output=capture, text=True)


def wait_healthy(timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/healthz", timeout=3).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def qdrant_counts() -> dict:
    """Vector counts per collection, read from Qdrant itself."""
    out = {}
    try:
        collections = httpx.get("http://localhost:16333/collections", timeout=10).json()
        for c in collections["result"]["collections"]:
            name = c["name"]
            info = httpx.get(f"http://localhost:16333/collections/{name}", timeout=10).json()
            out[name] = info["result"]["points_count"]
    except Exception as exc:
        out["_error"] = str(exc)[:80]
    return out


def pg_counts() -> dict:
    """Row counts straight from PostgreSQL, not through the application."""
    tables = ["clients", "memory_items", "documents", "document_chunks",
              "solution_candidates", "request_logs", "audit_events", "cost_records"]
    sql = " UNION ALL ".join(f"SELECT '{t}' AS t, count(*) FROM {t}" for t in tables)
    result = compose("exec", "-T", "postgres", "psql", "-U", "aihelper", "-d", "aihelper",
                     "-tAF,", "-c", sql)
    counts = {}
    for line in result.stdout.strip().splitlines():
        if "," in line:
            name, n = line.rsplit(",", 1)
            counts[name.strip()] = int(n)
    return counts


def main() -> int:
    ollama = FakeServer(OllamaHandler, 11600, bind="0.0.0.0").start()
    paid = FakeServer(AnthropicHandler, 11601, bind="0.0.0.0").start()
    hard = f"Explain the {HARD_TOPIC} rule and when it applies."
    try:
        section("Point the containerised app at reachable endpoints and restart it")
        override = ROOT / "docker-compose.audit.yml"
        override.write_text("""# Audit-environment override. NOT part of the product.
# Points the containerised gateway at stand-in model endpoints running on the
# host, and publishes Qdrant so the audit can count vectors independently of
# the application. This gate is about data surviving a restart.
services:
  ai-helper:
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      OLLAMA_URL: http://host.docker.internal:11600
      OLLAMA_ENABLED: "true"
      ANTHROPIC_ENABLED: "true"
      ANTHROPIC_API_KEY: sk-ant-audit-0000000000000000000000
      ANTHROPIC_BASE_URL: http://host.docker.internal:11601/v1
      AI_DAILY_API_BUDGET: "5.00"
      AUTO_PROMOTE: "true"
      MEMORY_SIMILARITY_THRESHOLD: "0.25"
      SOLUTION_REUSE_THRESHOLD: "0.45"
      RATE_LIMIT_BURST: "500"
      RATE_LIMIT_PER_MINUTE: "5000"
  qdrant:
    ports:
      - "127.0.0.1:16333:6333"
""")
        compose("-f", "docker-compose.yml", "-f", "docker-compose.audit.yml",
                "up", "-d", "ai-helper", "qdrant")
        check("the stack came back up", wait_healthy())

        # A unique id per run: create-client refuses a duplicate (correctly),
        # so a fixed name makes this script pass once and fail ever after.
        client_id = f"persist{int(time.time())}"
        created = compose("exec", "-T", "ai-helper", "python", "-m", "app.cli",
                          "create-client", client_id, "--admin", "--may-escalate")
        if not created.stdout.strip().startswith("{"):
            print(f"   {RED}create-client failed:{RESET} {created.stdout}{created.stderr}")
            return 1
        key = json.loads(created.stdout)["api_key"]
        c = httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {key}"}, timeout=60)

        # ------------------------------------------------- create real data
        section("Create real data through the containerised API")
        c.post("/api/v1/memory", json={"content": "The vault combination is 4815-1623-42.",
                                       "source": "handbook", "confidence": 0.95})
        c.post("/api/v1/documents", files={
            "file": ("policy.txt",
                     b"Invoice policy: invoices are numbered FV/YYYY/NN in sequence per year.",
                     "text/plain")})
        first = c.post("/api/v1/chat", json={"message": hard}).json()
        check("a paid fallback happened and was learned",
              first["route"] == "paid" and bool(first["solution_id"]),
              f"solution {first['solution_id']}")
        reuse = c.post("/api/v1/chat", json={"message": hard}).json()
        check("and is reused locally, free", reuse["memory_hit"] and reuse["route"] == "local")

        before_app = {
            "memory": len(c.get("/api/v1/memory").json()),
            "documents": len(c.get("/api/v1/documents").json()),
            "solutions": c.get("/api/v1/solutions/counts").json(),
            "requests": c.get("/api/v1/usage").json()["total_requests"],
            "spend": c.get("/api/v1/costs").json()["spent_today"],
            "audit": len(c.get("/api/v1/admin/audit", params={"limit": 500}).json()),
        }
        before_pg = pg_counts()
        before_qdrant = qdrant_counts()
        print(f"   {DIM}app     : {before_app}{RESET}")
        print(f"   {DIM}postgres: {before_pg}{RESET}")
        print(f"   {DIM}qdrant  : {before_qdrant}{RESET}")
        check("PostgreSQL holds the rows", before_pg.get("memory_items", 0) >= 1
              and before_pg.get("solution_candidates", 0) >= 1,
              f"{before_pg.get('memory_items')} memory, "
              f"{before_pg.get('solution_candidates')} solutions")
        check("Qdrant holds vectors", sum(v for k, v in before_qdrant.items()
                                          if not k.startswith("_")) > 0,
              str(before_qdrant))

        # ------------------------------------------------- restart for real
        section("docker compose down  →  docker compose up")
        down = compose("-f", "docker-compose.yml", "-f", "docker-compose.audit.yml", "down")
        check("containers stopped and were removed", down.returncode == 0)
        gone = compose("ps", "-q").stdout.strip()
        check("no container is left running", gone == "", gone[:60])
        print(f"   {DIM}volumes retained: "
              f"{subprocess.run(['docker','volume','ls','--filter','name=ai-helper','-q'], capture_output=True, text=True).stdout.split()}{RESET}")

        compose("-f", "docker-compose.yml", "-f", "docker-compose.audit.yml",
                "up", "-d", "postgres", "qdrant", "ollama", "ai-helper")
        check("the stack came back up after a full down/up", wait_healthy())

        # ----------------------------------------------------- verify
        section("Nothing was lost")
        after_pg = pg_counts()
        after_qdrant = qdrant_counts()
        print(f"   {DIM}postgres: {after_pg}{RESET}")
        print(f"   {DIM}qdrant  : {after_qdrant}{RESET}")

        for table in ("clients", "memory_items", "documents", "document_chunks",
                      "solution_candidates", "cost_records"):
            check(f"PostgreSQL {table}: {before_pg.get(table)} → {after_pg.get(table)}",
                  after_pg.get(table) == before_pg.get(table))
        check("PostgreSQL audit trail was not truncated",
              after_pg.get("audit_events", 0) >= before_pg.get("audit_events", 0),
              f"{before_pg.get('audit_events')} → {after_pg.get('audit_events')}")

        for name, count in before_qdrant.items():
            if name.startswith("_"):
                continue
            check(f"Qdrant {name}: {count} → {after_qdrant.get(name)}",
                  after_qdrant.get(name) == count)

        check("the same API key still authenticates", c.get("/api/v1/usage").status_code == 200)
        check("memory survived", len(c.get("/api/v1/memory").json()) == before_app["memory"])
        check("documents survived",
              len(c.get("/api/v1/documents").json()) == before_app["documents"])
        check("learned solutions survived",
              c.get("/api/v1/solutions/counts").json() == before_app["solutions"])
        check("recorded spend survived",
              c.get("/api/v1/costs").json()["spent_today"] == before_app["spend"])

        section("The learned answer is still reused, and still free")
        paid_before = len(paid.calls)
        after = c.post("/api/v1/chat", json={"message": hard}).json()
        check("memory hit after a container restart", after["memory_hit"] is True)
        check("answered locally", after["route"] == "local")
        check("NO paid call", len(paid.calls) == paid_before, f"paid calls still {len(paid.calls)}")
        check("semantic search works on the restarted Qdrant",
              bool(c.get("/api/v1/memory/search",
                         params={"q": "vault combination"}).json()["hits"]))

        section("Individual service restart")
        compose("restart", "postgres")
        time.sleep(6)
        check("the app recovers from a database restart", wait_healthy(90))
        check("data is still there after restarting PostgreSQL alone",
              len(c.get("/api/v1/memory").json()) == before_app["memory"])
        compose("restart", "qdrant")
        time.sleep(6)
        check("vectors are still there after restarting Qdrant alone",
              qdrant_counts() == after_qdrant, str(qdrant_counts()))

        failed = [r for r in results if not r[1]]
        print(f"\n{BOLD}{'='*70}{RESET}")
        if failed:
            print(f"{RED}{BOLD}{len(failed)} of {len(results)} checks FAILED{RESET}")
            for label, _ in failed:
                print(f"   {RED}✗{RESET} {label}")
            return 1
        print(f"{GREEN}{BOLD}CONTAINER PERSISTENCE PROVEN{RESET}  {len(results)}/{len(results)} checks")
        print(f"{BOLD}{'='*70}{RESET}")
        return 0
    finally:
        ollama.stop(); paid.stop()


if __name__ == "__main__":
    raise SystemExit(main())
