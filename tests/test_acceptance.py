"""The final acceptance test (work order §40 and §45), end to end over HTTP.

This is the demonstration the work order asks for, written as a test so it can
be re-run rather than performed once:

    first time   local fails -> paid API answers -> the solution is saved
    second time  memory hit  -> local answers    -> the paid API is NOT called
    dashboard    shows requests, local, fallbacks, memory hits, promoted, cost
    budget       exhausted -> paid stops, local keeps working
    restricted   data -> escalation blocked

Run it alone with:  pytest tests/test_acceptance.py -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import create_app
from tests.conftest import make_client
from tests.fakes import HARD_MARKER

HARD = f"Explain the {HARD_MARKER} rule and when it applies."


@pytest.fixture
def api(runtime, engine, db, settings):
    settings.ADMIN_PASSWORD_HASH = hash_password("dashboard-password-1")
    settings.RATE_LIMIT_BURST = 200
    application = create_app(settings, runtime=runtime)
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def key(db):
    _, plaintext = make_client(db, "acme", is_admin=True)
    db.commit()
    return plaintext


def auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def test_the_full_acceptance_scenario(api, key, paid_provider, local_provider, capsys):
    report: list[str] = []

    # ---------------------------------------------------- 1. first time
    first = api.post("/api/v1/chat", json={"message": HARD}, headers=auth(key)).json()
    report.append(
        f"1st ask   route={first['route']:6} provider={first['provider']:>10} "
        f"cost=${first['cost_usd']:.4f} escalation={first['escalation_reason']}"
    )
    assert first["route"] == "paid", "the local model should not have been able to answer this"
    assert paid_provider.call_count == 1
    assert first["cost_usd"] > 0
    assert first["solution_id"], "the fallback was not captured"

    solution = api.get(f"/api/v1/solutions/{first['solution_id']}", headers=auth(key)).json()
    report.append(
        f"          solution={solution['id']} status={solution['status']} "
        f"reproduced={solution['reproduction'].get('passed')}"
    )
    assert solution["status"] == "PROMOTED"

    # --------------------------------------------------- 2. second time
    calls_before = paid_provider.call_count
    second = api.post("/api/v1/chat", json={"message": HARD}, headers=auth(key)).json()
    report.append(
        f"2nd ask   route={second['route']:6} provider={second['provider']:>10} "
        f"cost=${second['cost_usd']:.4f} memory_hit={second['memory_hit']}"
    )
    assert second["route"] == "local", "the learned solution was not used"
    assert second["memory_hit"] is True
    assert second["cost_usd"] == 0.0
    assert paid_provider.call_count == calls_before, "THE PAID API WAS CALLED AGAIN"

    # --------------------------------------------------- 3. the dashboard
    usage = api.get("/api/v1/usage", headers=auth(key)).json()
    costs = api.get("/api/v1/costs", headers=auth(key)).json()
    report.append(
        f"dashboard requests={usage['total_requests']} local={usage['local_requests']} "
        f"fallbacks={usage['api_fallback_requests']} memory_hits={usage['memory_hits']} "
        f"promoted={usage['promoted_solutions']} cost=${costs['spent_today']:.4f}"
    )
    assert usage["total_requests"] == 2
    assert usage["local_requests"] == 1
    assert usage["api_fallback_requests"] == 1
    assert usage["memory_hits"] == 1
    assert usage["promoted_solutions"] == 1
    assert costs["spent_today"] > 0

    # --------------------------------------------- 4. the budget stops spend
    # A different hard question, so this exercises the budget rather than
    # being answered from the solution just learned.
    other_hard = "Explain the Fundusz Pracy minimum-wage threshold and who it exempts."
    local_provider.hard_topics.append("Fundusz Pracy minimum-wage threshold")

    api.app.state.settings.AI_DAILY_API_BUDGET = 0.0
    calls_before = paid_provider.call_count
    blocked = api.post(
        "/api/v1/chat", json={"message": other_hard}, headers=auth(key)
    ).json()
    report.append(
        f"budget    route={blocked['route']:6} blocked={blocked['escalation_blocked_reason']}"
    )
    assert paid_provider.call_count == calls_before, "money was spent past the budget"
    assert blocked["escalation_blocked_reason"] == "DAILY_BUDGET_EXHAUSTED"

    still_working = api.post(
        "/api/v1/chat", json={"message": "What is the capital of France?"}, headers=auth(key)
    ).json()
    report.append(f"local-on  route={still_working['route']:6} success={still_working['success']}")
    assert still_working["success"] is True, "the system stopped working when the budget ran out"

    # ------------------------------------------ 5. restricted data is blocked
    api.app.state.settings.AI_DAILY_API_BUDGET = 5.0
    calls_before = paid_provider.call_count
    restricted = api.post(
        "/api/v1/chat",
        json={"message": f"{other_hard} Our key is sk-abcdefghijklmnopqrstuvwxyz0123."},
        headers=auth(key),
    ).json()
    report.append(
        f"privacy   class={restricted['classification']} "
        f"blocked={restricted['escalation_blocked_reason']}"
    )
    assert restricted["classification"] == "RESTRICTED"
    assert restricted["escalation_blocked_reason"] == "CLASSIFICATION_BLOCKED"
    assert paid_provider.call_count == calls_before, "RESTRICTED DATA LEFT THE SYSTEM"

    with capsys.disabled():
        print("\n\n=== ACCEPTANCE SCENARIO ===")
        for line in report:
            print("  " + line)
        print("===========================\n")


def test_the_admin_dashboard_renders_the_acceptance_numbers(api, key, paid_provider):
    api.post("/api/v1/chat", json={"message": HARD}, headers=auth(key))
    api.post("/api/v1/chat", json={"message": HARD}, headers=auth(key))
    api.post("/api/v1/chat", json={"message": "2 + 2"}, headers=auth(key))

    api.post(
        "/admin/login",
        data={"username": "admin", "password": "dashboard-password-1"},
        follow_redirects=False,
    )
    page = api.get("/admin")
    assert page.status_code == 200
    for heading in [
        "AI requests",
        "API fallback",
        "Local success rate",
        "Memory hits",
        "Promoted solutions",
        "Why we are paying for AI",
        "Fallbacks",
    ]:
        assert heading in page.text, f"the dashboard is missing '{heading}'"

    overview = api.get("/api/v1/admin/overview", headers=auth(key)).json()
    assert overview["usage"]["total_requests"] == 3
    assert overview["usage"]["api_fallback_requests"] == 1
    assert overview["usage"]["promoted_solutions"] == 1
    assert overview["spend"]["spent_today"] > 0
