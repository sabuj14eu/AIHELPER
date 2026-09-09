"""The request session commits BEFORE the response leaves (app/api/transaction.py).

Found by the real-model gate: FastAPI ≥ 0.118 runs a yield dependency's exit
code after the response is sent, so the commit in `db_dep` happened after the
caller already had its 200. The test client cannot observe that ordering (it
waits for the whole request), so these tests drive the middleware directly
with a recording session and assert the order of events.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.api.transaction import STATE_KEY, CommitBeforeResponse


class RecordingSession:
    def __init__(self, fail_commit: bool = False):
        self.events: list[str] = []
        self.fail_commit = fail_commit

    def commit(self):
        self.events.append("commit")
        if self.fail_commit:
            raise RuntimeError("database went away")

    def rollback(self):
        self.events.append("rollback")


def _app_that_responds(status: int, session: RecordingSession, body: bytes = b'{"ok": true}'):
    async def app(scope, receive, send):
        scope["state"][STATE_KEY] = session
        session.events.append("route")
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
        session.events.append("response.start sent")
        await send({"type": "http.response.body", "body": body, "more_body": False})

    return app


def _drive(app, session: RecordingSession):
    sent: list[dict] = []

    async def send(message):
        sent.append(message)
        session.events.append(f"client got {message['type']}")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "POST", "path": "/api/v1/chat", "headers": [], "state": {}}
    asyncio.run(CommitBeforeResponse(app)(scope, receive, send))
    return sent


class TestCommitBeforeResponse:
    def test_a_successful_response_is_committed_before_its_first_byte_leaves(self):
        session = RecordingSession()
        sent = _drive(_app_that_responds(200, session), session)
        assert session.events == [
            "route",
            "commit",                       # before the client sees anything
            "client got http.response.start",
            "response.start sent",
            "client got http.response.body",
        ]
        assert sent[0]["status"] == 200

    def test_a_failed_commit_becomes_a_500_and_the_original_body_is_never_sent(self):
        session = RecordingSession(fail_commit=True)
        sent = _drive(_app_that_responds(200, session, body=b'{"route": "paid", "cost_usd": 0.5}'), session)
        assert "rollback" in session.events
        assert [m["status"] for m in sent if m["type"] == "http.response.start"] == [500]
        bodies = [m["body"] for m in sent if m["type"] == "http.response.body"]
        assert len(bodies) == 1
        assert json.loads(bodies[0])["code"] == "internal_error"
        assert b"paid" not in bodies[0]

    @pytest.mark.parametrize("status", [401, 404, 422, 429, 500, 503])
    def test_an_error_response_rolls_the_session_back_instead_of_committing(self, status):
        session = RecordingSession()
        sent = _drive(_app_that_responds(status, session), session)
        assert "rollback" in session.events and "commit" not in session.events
        assert sent[0]["status"] == status

    def test_a_request_without_a_session_passes_through_untouched(self):
        session = RecordingSession()

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"x", "more_body": False})

        sent = _drive(app, session)
        assert [m["type"] for m in sent] == ["http.response.start", "http.response.body"]
        assert "commit" not in session.events and "rollback" not in session.events

    def test_non_http_scopes_are_passed_through(self):
        seen = {}

        async def app(scope, receive, send):
            seen["scope"] = scope["type"]

        asyncio.run(CommitBeforeResponse(app)({"type": "lifespan"}, None, None))
        assert seen["scope"] == "lifespan"
