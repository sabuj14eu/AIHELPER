"""End-to-end tests through the HTTP surface."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.main import create_app
from tests.conftest import make_client


@pytest.fixture
def api(runtime, engine, db, settings):
    settings.ADMIN_PASSWORD_HASH = hash_password("dashboard-password-1")
    application = create_app(settings, runtime=runtime)
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def keys(db):
    _, user_key = make_client(db, "acme")
    _, admin_key = make_client(db, "root", is_admin=True)
    db.commit()
    return {"user": user_key, "admin": admin_key}


def auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def test_root_and_health(api):
    assert api.get("/").json()["local_first"] is True
    body = api.get("/health").json()
    names = {c["name"] for c in body["components"]}
    assert {"gateway", "database", "ollama", "anthropic", "embedder"} <= names
    assert api.get("/healthz").json() == {"status": "alive"}


def test_chat_requires_a_key(api):
    response = api.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_failed"


def test_chat_rejects_a_forged_key(api, keys):
    response = api.post(
        "/api/v1/chat", json={"message": "hello"}, headers=auth("ahk_deadbeef.notarealsecret")
    )
    assert response.status_code == 401


def test_chat_answers_with_a_tool_and_costs_nothing(api, keys, paid_provider):
    response = api.post(
        "/api/v1/chat", json={"message": "What is 12 * 12?"}, headers=auth(keys["user"])
    )
    body = response.json()
    assert response.status_code == 200
    assert body["answer"] == "144"
    assert body["route"] == "tool"
    assert body["cost_usd"] == 0.0
    assert paid_provider.call_count == 0
    assert response.headers["x-request-id"]


def test_chat_rejects_an_unknown_field(api, keys):
    response = api.post(
        "/api/v1/chat", json={"message": "hi", "nonsense": 1}, headers=auth(keys["user"])
    )
    assert response.status_code == 422


def test_document_upload_and_search(api, keys):
    text = (
        "The ZUS social contribution base for 2026 is 5203.80 PLN. "
        "The Fundusz Pracy is due only from a base at or above the minimum wage."
    )
    response = api.post(
        "/api/v1/documents",
        files={"file": ("zus.txt", io.BytesIO(text.encode()), "text/plain")},
        data={"namespace": "default"},
        headers=auth(keys["user"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["chunks"] >= 1 and body["indexed"] == body["chunks"]

    listing = api.get("/api/v1/documents", headers=auth(keys["user"])).json()
    assert len(listing) == 1

    hits = api.get(
        "/api/v1/memory/search", params={"q": "ZUS social contribution base"}, headers=auth(keys["user"])
    ).json()
    assert any(h["source"] == "document" for h in hits["hits"])


def test_duplicate_upload_is_not_stored_twice(api, keys):
    payload = {"file": ("a.txt", io.BytesIO(b"exactly the same bytes"), "text/plain")}
    first = api.post("/api/v1/documents", files=payload, headers=auth(keys["user"])).json()
    payload = {"file": ("a.txt", io.BytesIO(b"exactly the same bytes"), "text/plain")}
    second = api.post("/api/v1/documents", files=payload, headers=auth(keys["user"])).json()
    assert second["duplicate"] is True
    assert second["document_id"] == first["document_id"]


def test_unsupported_upload_is_refused(api, keys):
    response = api.post(
        "/api/v1/documents",
        files={"file": ("virus.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers=auth(keys["user"]),
    )
    assert response.status_code == 422
    assert "unsupported file type" in response.json()["error"]


def test_memory_write_and_list(api, keys):
    response = api.post(
        "/api/v1/memory",
        json={
            "content": "Invoices are numbered FV/YYYY/NN.",
            "source": "operations handbook",
            "confidence": 0.9,
            "kind": "fact",
        },
        headers=auth(keys["user"]),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"
    assert len(api.get("/api/v1/memory", headers=auth(keys["user"])).json()) == 1


def test_memory_write_rejects_impossible_confidence(api, keys):
    response = api.post(
        "/api/v1/memory",
        json={"content": "x", "source": "s", "confidence": 1.5},
        headers=auth(keys["user"]),
    )
    assert response.status_code == 422


def test_usage_and_cost_endpoints(api, keys):
    api.post("/api/v1/chat", json={"message": "2+2"}, headers=auth(keys["user"]))
    usage = api.get("/api/v1/usage", headers=auth(keys["user"])).json()
    assert usage["total_requests"] >= 1
    assert usage["api_fallback_requests"] == 0
    costs = api.get("/api/v1/costs", headers=auth(keys["user"])).json()
    assert costs["spent_today"] == 0.0
    assert costs["paid_disabled_by_budget"] is False


def test_models_tools_and_agents(api, keys):
    models = api.get("/api/v1/models", headers=auth(keys["user"])).json()
    assert models["local_available"] is True
    tools = api.get("/api/v1/tools", headers=auth(keys["user"])).json()
    assert any(t["name"] == "calculator" for t in tools)
    agents = api.get("/api/v1/agents", headers=auth(keys["user"])).json()
    assert {a["name"] for a in agents} == {
        "general", "research", "document", "developer",
        "brother", "trading", "architect", "social",
    }


def test_admin_endpoints_require_an_admin_key(api, keys):
    assert api.get("/api/v1/admin/clients", headers=auth(keys["user"])).status_code == 403
    assert api.get("/api/v1/admin/clients", headers=auth(keys["admin"])).status_code == 200


def test_admin_can_create_and_revoke_a_client(api, keys):
    created = api.post(
        "/api/v1/admin/clients", params={"client_id": "newapp"}, headers=auth(keys["admin"])
    )
    assert created.status_code == 201
    issued = created.json()["api_key"]
    assert api.post("/api/v1/chat", json={"message": "2+2"}, headers=auth(issued)).status_code == 200

    api.post("/api/v1/admin/clients/newapp/revoke", headers=auth(keys["admin"]))
    assert api.post("/api/v1/chat", json={"message": "2+2"}, headers=auth(issued)).status_code == 401


def test_async_task_round_trip(api, keys):
    import time

    created = api.post(
        "/api/v1/tasks", json={"message": "What is 7 * 6?"}, headers=auth(keys["user"])
    )
    assert created.status_code == 202
    task_id = created.json()["task_id"]
    for _ in range(300):
        body = api.get(f"/api/v1/tasks/{task_id}", headers=auth(keys["user"])).json()
        if body["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.01)
    assert body["status"] == "succeeded", body.get("error") or body
    assert body["result"]["answer"] == "42"


def test_admin_dashboard_login_flow(api):
    assert api.get("/admin", follow_redirects=False).status_code == 401
    assert api.get("/admin/login").status_code == 200
    bad = api.post("/admin/login", data={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401
    good = api.post(
        "/admin/login",
        data={"username": "admin", "password": "dashboard-password-1"},
        follow_redirects=False,
    )
    assert good.status_code == 303
    page = api.get("/admin")
    assert page.status_code == 200
    assert "Local success rate" in page.text
    for path in ("/admin/solutions", "/admin/clients", "/admin/audit"):
        assert api.get(path).status_code == 200


# ------------------------------------------------------------------ Brother
class TestBrotherChat:
    """The dashboard's own chat runs as the personal client through the same ladder."""

    @pytest.fixture
    def signed_in(self, api, settings):
        from app.core.security import hash_password

        settings.ADMIN_PASSWORD_HASH = hash_password("dashboard-password-1")
        response = api.post(
            "/admin/login",
            data={"username": settings.ADMIN_USERNAME, "password": "dashboard-password-1"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        return api

    def test_the_page_needs_a_session(self, api):
        assert api.get("/admin/chat", follow_redirects=False).status_code == 401
        assert (
            api.post("/admin/chat/ask", json={"message": "hi"}, follow_redirects=False).status_code
            == 401
        )

    def test_the_page_explains_when_the_personal_client_is_missing(self, signed_in):
        page = signed_in.get("/admin/chat")
        assert page.status_code == 200
        assert "bootstrap-brother" in page.text
        refused = signed_in.post("/admin/chat/ask", json={"message": "hello"})
        assert refused.status_code == 503
        assert "bootstrap-brother" in refused.json()["error"]

    def test_a_question_runs_as_the_personal_client_with_the_default_agent(
        self, signed_in, db, settings, local_provider, paid_provider
    ):
        make_client(db, settings.PERSONAL_CLIENT_ID)
        db.commit()
        page = signed_in.get("/admin/chat")
        assert page.status_code == 200 and "bootstrap-brother" not in page.text
        assert 'value="brother" selected' in page.text

        answer = signed_in.post("/admin/chat/ask", json={"message": "What is the capital of France?"})
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["agent"] == "brother"
        assert body["route"] == "local" and "Paris" in body["answer"]
        assert body["conversation_id"]
        assert paid_provider.call_count == 0
        assert "Never infer from silence" in local_provider.calls[-1].messages[0].content

        # The conversation continues, and the log names the personal client.
        follow = signed_in.post(
            "/admin/chat/ask",
            json={"message": "And its population?", "conversation_id": body["conversation_id"]},
        )
        assert follow.status_code == 200
        assert follow.json()["conversation_id"] == body["conversation_id"]
        from app.database.models import RequestLog

        rows = list(db.scalars(select(RequestLog)))
        assert rows and all(r.client_id == settings.PERSONAL_CLIENT_ID for r in rows)

    def test_an_unknown_agent_is_refused(self, signed_in, db, settings):
        make_client(db, settings.PERSONAL_CLIENT_ID)
        db.commit()
        refused = signed_in.post("/admin/chat/ask", json={"message": "hi", "agent": "nope"})
        assert refused.status_code == 403

    def test_a_tool_answer_stays_free(self, signed_in, db, settings, local_provider):
        make_client(db, settings.PERSONAL_CLIENT_ID)
        db.commit()
        answer = signed_in.post(
            "/admin/chat/ask", json={"message": "What is 1200 * 0.23?", "agent": "trading"}
        )
        assert answer.json()["route"] == "tool" and answer.json()["answer"] == "276"
        assert local_provider.calls == []
