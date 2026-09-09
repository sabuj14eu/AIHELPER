"""Regression tests for the findings of the final audit (2026-09-08).

Each test here failed against the code as it stood at commit b36ac85 and passes
after the fix that accompanies it. They are grouped by finding id; the finding
ids match audit/AUDIT_REPORT.md.

The most important is F1: retrieved context (a memory item, a document chunk, a
learned solution) used to leave the system with an escalated prompt without its
own classification being checked, so a RESTRICTED memory item retrieved for an
INTERNAL question was sent to a paid provider.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.audit import AUTH_FAILURE, RATE_LIMITED
from app.core.security import hash_password
from app.database.models import AuditEvent, CostRecord, MemoryItem
from app.gateway.router import GatewayRequest
from app.main import create_app
from app.memory.long_term import LongTermMemory
from tests.conftest import make_client
from tests.fakes import HARD_MARKER


@pytest.fixture
def api(runtime, engine, db, settings):
    settings.ADMIN_PASSWORD_HASH = hash_password("dashboard-password-1")
    settings.RATE_LIMIT_BURST = 3
    application = create_app(settings, runtime=runtime)
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client


def auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


# --------------------------------------------------------------------------
# F1 — retrieved context bypassed the classification gate.
# --------------------------------------------------------------------------
class TestContextClassificationGate:
    def test_restricted_memory_never_reaches_a_paid_provider(
        self, runtime, db, local_provider, paid_provider
    ):
        client, _ = make_client(db, "ctxleak", may_escalate=True)
        LongTermMemory(db, client.client_id).write(
            f"{HARD_MARKER} internal note: the secret margin is forty-two percent",
            source="probe",
            confidence=0.9,
            sensitivity="RESTRICTED",
        )
        services = runtime.for_session(db, client.client_id)
        item = db.scalars(select(MemoryItem)).first()
        services.retriever.index_memory(item)
        local_provider.answer_override = "INSUFFICIENT_CONTEXT — cannot"

        resp = services.router.handle(
            GatewayRequest(message=f"Explain the {HARD_MARKER} rule", client=client)
        )

        # The RESTRICTED memory item raised the whole request to RESTRICTED, so
        # escalation was refused rather than the note being sent out.
        assert resp.classification.value == "RESTRICTED"
        assert resp.escalation_blocked_reason is not None
        sent = "\n".join(m.content for c in paid_provider.calls for m in c.messages)
        assert "forty-two percent" not in sent

    def test_confidential_document_chunk_is_not_sent_externally_by_default(
        self, runtime, db, local_provider, paid_provider
    ):
        client, _ = make_client(db, "docleak", may_escalate=True)
        services = runtime.for_session(db, client.client_id)
        services.ingestor.ingest(
            (
                f"{HARD_MARKER} contract clause: the buyer pays a confidential rebate of "
                "nineteen percent to the seller."
            ).encode(),
            "contract.txt",
            classification="CONFIDENTIAL",
        )
        local_provider.answer_override = "INSUFFICIENT_CONTEXT — cannot"

        resp = services.router.handle(
            GatewayRequest(message=f"What does the {HARD_MARKER} clause say?", client=client)
        )

        # EXTERNAL_ALLOWED_CLASSIFICATIONS defaults to PUBLIC,INTERNAL, so a
        # CONFIDENTIAL chunk lifts the request out of what may leave.
        assert resp.classification.value == "CONFIDENTIAL"
        sent = "\n".join(m.content for c in paid_provider.calls for m in c.messages)
        assert "nineteen percent" not in sent

    def test_allowed_context_still_escalates(self, runtime, db, local_provider, paid_provider):
        """The gate must not become a blanket block: INTERNAL context still goes."""
        client, _ = make_client(db, "ok", may_escalate=True)
        services = runtime.for_session(db, client.client_id)
        LongTermMemory(db, client.client_id).write(
            f"{HARD_MARKER} background reading, nothing sensitive here",
            source="probe",
            confidence=0.9,
            sensitivity="INTERNAL",
        )
        services.retriever.index_memory(db.scalars(select(MemoryItem)).first())
        local_provider.answer_override = "INSUFFICIENT_CONTEXT — cannot"

        resp = services.router.handle(
            GatewayRequest(message=f"Explain the {HARD_MARKER} rule", client=client)
        )
        assert resp.classification.value == "INTERNAL"
        assert paid_provider.call_count == 1


# --------------------------------------------------------------------------
# F2 — refusals raised out of the auth layer left no audit row (rolled back).
# --------------------------------------------------------------------------
class TestRefusalsAreDurablyAudited:
    def test_an_authentication_failure_leaves_a_committed_audit_row(self, api, db):
        assert (
            api.post(
                "/api/v1/chat",
                json={"message": "hi"},
                headers=auth("ahk_aaaaaaaaaaaa.wrongsecret"),
            ).status_code
            == 401
        )
        db.expire_all()
        assert list(db.scalars(select(AuditEvent).where(AuditEvent.action == AUTH_FAILURE)))

    def test_a_rate_limit_block_leaves_a_committed_audit_row(self, api, db):
        _, key = make_client(db, "burst")
        db.commit()
        codes = [
            api.post("/api/v1/chat", json={"message": "2+2"}, headers=auth(key)).status_code
            for _ in range(6)
        ]
        assert 429 in codes
        db.expire_all()
        assert list(db.scalars(select(AuditEvent).where(AuditEvent.action == RATE_LIMITED)))


# --------------------------------------------------------------------------
# F3 — a recorded charge was discarded if a later step in the request raised.
# --------------------------------------------------------------------------
def test_a_recorded_charge_survives_a_failure_in_post_call_bookkeeping(
    api, db, runtime, local_provider, paid_provider, monkeypatch
):
    _, key = make_client(db, "money", may_escalate=True)
    db.commit()
    local_provider.answer_override = "INSUFFICIENT_CONTEXT — cannot"
    from app.gateway import router as router_mod

    def boom(*_a, **_k):
        raise RuntimeError("a bug in solution capture, after the money was spent")

    monkeypatch.setattr(router_mod.GatewayRouter, "_learn", boom)
    resp = api.post(
        "/api/v1/chat", json={"message": f"Explain the {HARD_MARKER} rule"}, headers=auth(key)
    )
    assert resp.status_code == 200
    assert paid_provider.call_count == 1
    db.expire_all()
    assert list(db.scalars(select(CostRecord))), "the CostRecord for a billed call was lost"


# --------------------------------------------------------------------------
# F4 — input-validation paths that returned 500 instead of a clean 4xx.
# --------------------------------------------------------------------------
class TestBadInputIsAFourHundred:
    def test_a_cross_client_conversation_id_is_not_found_not_a_500(self, api, db):
        _, a = make_client(db, "convA")
        _, b = make_client(db, "convB")
        db.commit()
        assert (
            api.post(
                "/api/v1/chat",
                json={"message": "2+2", "conversation_id": "shared-conv"},
                headers=auth(a),
            ).status_code
            == 200
        )
        r = api.post(
            "/api/v1/chat",
            json={"message": "3+3", "conversation_id": "shared-conv"},
            headers=auth(b),
        )
        assert r.status_code == 404

    def test_a_bad_classification_on_upload_is_a_422(self, api, db):
        _, key = make_client(db, "upl")
        db.commit()
        r = api.post(
            "/api/v1/documents",
            files={"file": ("a.txt", b"hello world text")},
            data={"classification": "BOGUS"},
            headers=auth(key),
        )
        assert r.status_code == 422

    def test_a_bad_classification_on_admin_create_client_is_a_422(self, api, db):
        _, admin_key = make_client(db, "root", is_admin=True)
        db.commit()
        r = api.post(
            "/api/v1/admin/clients",
            params={"client_id": "x1", "max_external_classification": "NOPE"},
            headers=auth(admin_key),
        )
        assert r.status_code == 422


# --------------------------------------------------------------------------
# F5 — /costs disclosed every client's provider/model breakdown to any client.
# --------------------------------------------------------------------------
def test_costs_breakdown_is_scoped_to_the_client_for_a_non_admin(
    api, db, runtime, local_provider, paid_provider
):
    _, spender = make_client(db, "spender", may_escalate=True)
    _, other = make_client(db, "other", may_escalate=False)
    db.commit()
    local_provider.answer_override = "INSUFFICIENT_CONTEXT — cannot"
    api.post(
        "/api/v1/chat", json={"message": f"Explain the {HARD_MARKER} rule"}, headers=auth(spender)
    )
    body = api.get("/api/v1/costs", headers=auth(other)).json()
    assert body["by_provider"] == []
    assert body["by_escalation_reason"] == []


# --------------------------------------------------------------------------
# F6 (real-model gate) — the request session committed AFTER the response.
# FastAPI ≥ 0.118 runs a yield dependency's exit code after the response has
# been sent, so a caller could hold a 200 for a billed call whose rows had not
# been committed — or, if that commit failed, never would be. The unit tests
# in tests/unit/test_transaction.py pin the ordering; this pins the outcome
# through the real app: a commit that fails cannot produce a 200.
# --------------------------------------------------------------------------
class TestCommitFailureCannotAnswerSuccess:
    def test_a_failed_commit_is_a_500_and_nothing_is_recorded(self, api, db, monkeypatch):
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from app.database.models import RequestLog

        _client, key = make_client(db, "commitfail", may_escalate=False)
        db.commit()
        real_commit = Session.commit
        armed = {"on": False}

        def failing_commit(self):
            if armed["on"]:
                raise RuntimeError("database went away at commit time")
            return real_commit(self)

        monkeypatch.setattr(Session, "commit", failing_commit)
        armed["on"] = True
        try:
            response = api.post("/api/v1/chat", json={"message": "hello there"}, headers=auth(key))
        finally:
            armed["on"] = False

        assert response.status_code == 500
        assert response.json()["code"] == "internal_error"
        assert "route" not in response.json()
        # The request was answered by the local fake provider, but because its
        # log could not be committed the caller was told so — and no row exists.
        assert db.scalars(select(RequestLog).where(RequestLog.client_id == "commitfail")).all() == []

    def test_a_successful_request_is_visible_to_the_very_next_read(self, api, db):
        from sqlalchemy import select

        from app.database.models import RequestLog

        _client, key = make_client(db, "commitok", may_escalate=False)
        db.commit()
        response = api.post("/api/v1/chat", json={"message": "hello there"}, headers=auth(key))
        assert response.status_code == 200
        rows = db.scalars(select(RequestLog).where(RequestLog.client_id == "commitok")).all()
        assert len(rows) == 1 and rows[0].request_id == response.json()["request_id"]
