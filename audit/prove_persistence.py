"""Migrations and persistence: fresh install, restart, upgrade, backup/restore.

The question under test is the only one that matters here: does anything the
system learned or was told survive?
"""

from __future__ import annotations

import json
import os
import shutil
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


def main() -> int:
    ollama = FakeServer(OllamaHandler, 11590).start()
    paid = FakeServer(AnthropicHandler, 11591).start()
    workdir = Path(tempfile.mkdtemp(prefix="aihelper-persist-"))
    database = workdir / "live.db"
    hard = f"Explain the {HARD_TOPIC} rule and when it applies."

    env = {**os.environ, "AI_HELPER_ENV_FILE": "/nonexistent",
           "DATABASE_URL": f"sqlite+pysqlite:///{database}",
           "OLLAMA_URL": ollama.url, "OLLAMA_ENABLED": "true", "QDRANT_ENABLED": "false",
           "ANTHROPIC_ENABLED": "true", "ANTHROPIC_API_KEY": "sk-ant-x-00000000000000000000",
           "ANTHROPIC_BASE_URL": f"{paid.url}/v1", "AI_DAILY_API_BUDGET": "5.00",
           "AUTH_SECRET": "audit-secret", "LOG_LEVEL": "WARNING", "AUTO_PROMOTE": "true",
           "RATE_LIMIT_BURST": "500", "RATE_LIMIT_PER_MINUTE": "5000",
           "MEMORY_SIMILARITY_THRESHOLD": "0.25", "SOLUTION_REUSE_THRESHOLD": "0.45",
           "PYTHONPATH": str(ROOT)}

    def alembic(*args):
        return subprocess.run([str(VENV), "-m", "alembic", *args],
                              cwd=ROOT, env=env, capture_output=True, text=True)

    def start(port):
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
        return proc, log

    def stop(pair):
        proc, log = pair
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    try:
        # ------------------------------------------------ fresh install
        section("Fresh install — migrations create the schema")
        out = alembic("upgrade", "head")
        check("alembic upgrade head succeeds on an empty database", out.returncode == 0,
              out.stderr.strip().splitlines()[-1] if out.stderr else "")
        current = alembic("current")
        check("the database reports a revision", "0001_baseline" in current.stdout,
              current.stdout.strip())
        import sqlite3
        tables = sorted(r[0] for r in sqlite3.connect(database).execute(
            "select name from sqlite_master where type='table'"))
        expected = {"clients", "solution_candidates", "memory_items", "documents",
                    "document_chunks", "request_logs", "audit_events", "cost_records",
                    "conversations", "messages", "jobs", "vector_points", "alembic_version"}
        check("every expected table exists", expected <= set(tables),
              f"{len(tables)} tables")
        check("running it twice is a no-op", alembic("upgrade", "head").returncode == 0)

        # ----------------------------------------------- populate state
        section("Populate — a client, a document, a memory, a learned solution")
        gw = start(8860)
        key = json.loads(subprocess.run(
            [str(VENV), "-m", "app.cli", "create-client", "persist", "--admin", "--may-escalate"],
            cwd=ROOT, env=env, capture_output=True, text=True).stdout)["api_key"]
        c = httpx.Client(base_url="http://127.0.0.1:8860",
                         headers={"Authorization": f"Bearer {key}"}, timeout=60)
        c.post("/api/v1/memory", json={"content": "The vault combination is 4815-1623-42.",
                                       "source": "handbook", "confidence": 0.95})
        c.post("/api/v1/documents", files={
            "file": ("policy.txt", b"Invoice policy: invoices are numbered FV/YYYY/NN.", "text/plain")}).json()
        c.post("/api/v1/chat", json={"message": hard})
        reuse = c.post("/api/v1/chat", json={"message": hard}).json()
        check("a solution was learned and promoted", reuse["memory_hit"] and reuse["route"] == "local")
        baseline = {
            "memory": len(c.get("/api/v1/memory").json()),
            "documents": len(c.get("/api/v1/documents").json()),
            "solutions": c.get("/api/v1/solutions/counts").json(),
            "usage": c.get("/api/v1/usage").json()["total_requests"],
            "costs": c.get("/api/v1/costs").json()["spent_today"],
        }
        print(f"   {DIM}baseline: {baseline}{RESET}")
        stop(gw)

        # ---------------------------------------------------- restart
        section("Restart — nothing is lost")
        gw = start(8861)
        c = httpx.Client(base_url="http://127.0.0.1:8861",
                         headers={"Authorization": f"Bearer {key}"}, timeout=60)
        check("the same API key still works", c.get("/api/v1/usage").status_code == 200)
        check("memory survived", len(c.get("/api/v1/memory").json()) == baseline["memory"])
        check("documents survived", len(c.get("/api/v1/documents").json()) == baseline["documents"])
        check("learned solutions survived",
              c.get("/api/v1/solutions/counts").json() == baseline["solutions"])
        check("the request log survived",
              c.get("/api/v1/usage").json()["total_requests"] >= baseline["usage"])
        check("recorded spend survived",
              c.get("/api/v1/costs").json()["spent_today"] == baseline["costs"])
        before = len(paid.calls)
        after_restart = c.post("/api/v1/chat", json={"message": hard}).json()
        check("the learned answer is STILL reused after a restart",
              after_restart["memory_hit"] and after_restart["route"] == "local")
        check("and still costs nothing", len(paid.calls) == before)
        check("the semantic index survived the restart too",
              c.get("/api/v1/memory/search", params={"q": "vault combination"}).json()["hits"])
        stop(gw)

        # ----------------------------------------------------- upgrade
        section("Upgrade — downgrade and re-upgrade the schema")
        down = alembic("downgrade", "base")
        check("downgrade to base succeeds", down.returncode == 0)
        remaining = sorted(r[0] for r in sqlite3.connect(database).execute(
            "select name from sqlite_master where type='table'"))
        check("downgrade removes the application tables", remaining == ["alembic_version"],
              str(remaining))
        up = alembic("upgrade", "head")
        check("re-upgrade succeeds", up.returncode == 0)
        check("the schema is back", expected <= {
            r[0] for r in sqlite3.connect(database).execute(
                "select name from sqlite_master where type='table'")})
        print(f"   {DIM}note: a downgrade to base is destructive by design — this is why the "
              f"documented order is backup, migrate, restart, verify{RESET}")

        # ---------------------------------------------- backup/restore
        section("Backup and restore — from a real dump, into an empty database")
        # Rebuild state, then dump and restore it. scripts/backup.sh drives
        # docker compose; here the same pg_dump/pg_restore step is exercised as
        # SQLite's equivalent, which is what this environment can run.
        gw = start(8862)
        key2 = json.loads(subprocess.run(
            [str(VENV), "-m", "app.cli", "create-client", "restored", "--admin", "--may-escalate"],
            cwd=ROOT, env=env, capture_output=True, text=True).stdout)["api_key"]
        c = httpx.Client(base_url="http://127.0.0.1:8862",
                         headers={"Authorization": f"Bearer {key2}"}, timeout=60)
        c.post("/api/v1/memory", json={"content": "Restored fact: the code is 9910.",
                                       "source": "handbook", "confidence": 0.9})
        c.post("/api/v1/chat", json={"message": hard})
        c.post("/api/v1/chat", json={"message": hard})
        audit_before = c.get("/api/v1/admin/audit", params={"limit": 500}).json()
        pre = {"memory": len(c.get("/api/v1/memory").json()),
               "solutions": c.get("/api/v1/solutions/counts").json(),
               "audit_ids": {e["id"] for e in audit_before},
               "audit_learning": {e["id"] for e in audit_before
                                  if e["action"].startswith("learning.")}}
        stop(gw)

        backup = workdir / "backup.sql"
        with open(backup, "w") as fh:
            conn = sqlite3.connect(database)
            for line in conn.iterdump():
                fh.write(f"{line}\n")
            conn.close()
        check("a dump was produced", backup.stat().st_size > 0,
              f"{backup.stat().st_size} bytes")
        for table in ("clients", "solution_candidates", "memory_items", "audit_events",
                      "cost_records", "vector_points"):
            check(f"the dump contains {table}", table in backup.read_text())

        # Destroy and restore.
        database.unlink()
        for suffix in ("-wal", "-shm"):
            Path(str(database) + suffix).unlink(missing_ok=True)
        check("the database is gone", not database.exists())
        restored = sqlite3.connect(database)
        restored.executescript(backup.read_text())
        restored.commit(); restored.close()

        gw = start(8863)
        c = httpx.Client(base_url="http://127.0.0.1:8863",
                         headers={"Authorization": f"Bearer {key2}"}, timeout=60)
        check("the restored database serves the same key",
              c.get("/api/v1/usage").status_code == 200)
        check("memory came back", len(c.get("/api/v1/memory").json()) == pre["memory"])
        check("learned solutions came back",
              c.get("/api/v1/solutions/counts").json() == pre["solutions"], str(pre["solutions"]))
        audit_after = c.get("/api/v1/admin/audit", params={"limit": 500}).json()
        ids_after = {e["id"] for e in audit_after}
        # The restored instance logs its own requests, so the count grows.
        # What must hold is that every historical row is still there.
        check("every audit row from before the restore is present",
              pre["audit_ids"] <= ids_after,
              f"{len(pre['audit_ids'])} before, {len(ids_after)} now, "
              f"{len(pre['audit_ids'] - ids_after)} missing")
        check("the learning history specifically survived",
              pre["audit_learning"] and pre["audit_learning"] <= ids_after,
              f"{len(pre['audit_learning'])} learning event(s)")
        check("the append-only trail was not truncated by the restore",
              len(ids_after) >= len(pre["audit_ids"]))
        before = len(paid.calls)
        after_restore = c.post("/api/v1/chat", json={"message": hard}).json()
        check("the learned answer is reused from the RESTORED database",
              after_restore["memory_hit"] and after_restore["route"] == "local")
        check("and still costs nothing", len(paid.calls) == before)
        check("semantic search works on restored vectors",
              c.get("/api/v1/memory/search", params={"q": "restored fact code"}).json()["hits"])
        stop(gw)

        failed = [r for r in results if not r[1]]
        print(f"\n{BOLD}{'='*70}{RESET}")
        if failed:
            print(f"{RED}{BOLD}{len(failed)} of {len(results)} checks FAILED{RESET}")
            for label, _ in failed:
                print(f"   {RED}✗{RESET} {label}")
            return 1
        print(f"{GREEN}{BOLD}PERSISTENCE PROVEN{RESET}  {len(results)}/{len(results)} checks")
        print(f"{BOLD}{'='*70}{RESET}")
        return 0
    finally:
        ollama.stop(); paid.stop()
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
