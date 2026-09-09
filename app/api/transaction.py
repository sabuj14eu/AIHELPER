"""Commit the request's database session BEFORE the response leaves.

FastAPI 0.118 and later run the exit code of a ``yield`` dependency *after*
the response has been sent. ``db_dep`` commits in that exit code, which had
two consequences, both found by the real-model gate rather than by the test
suite (the test client waits for the whole request, exit code included, so
it can never observe them):

* A caller could receive the response before its rows were committed. A read
  issued immediately afterwards did not see the write — the audit suite
  failed, once, on exactly that race.
* A commit that failed after the response was sent could not change the
  status code. A paid, billed call would then have answered 200 while its
  CostRecord and audit rows were rolled back — money spent with no record,
  the class of defect the cost layer exists to make impossible.

So the commit is moved to the first byte of the response. On a 2xx/3xx the
session is committed before ``http.response.start`` is forwarded; if that
commit raises, the session is rolled back and a 500 is sent instead, so
nothing half-written is ever acknowledged. On a 4xx/5xx the session is rolled
back, which is what the dependency's exception branch did when it still ran
first. The dependency's own commit/rollback stays as a harmless no-op.
"""

from __future__ import annotations

import json

from starlette.concurrency import run_in_threadpool

from app.core.logging import get_logger, request_id_var

log = get_logger("transaction")

STATE_KEY = "db_session"


class CommitBeforeResponse:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        replaced = False

        async def send_wrapper(message):
            nonlocal replaced
            if message["type"] == "http.response.start":
                session = state.get(STATE_KEY)
                if session is not None:
                    if message["status"] < 400:
                        try:
                            await run_in_threadpool(session.commit)
                        except Exception as exc:
                            log.error("commit_failed_before_response", error=type(exc).__name__)
                            await run_in_threadpool(session.rollback)
                            replaced = True
                            body = json.dumps(
                                {
                                    "error": "the request could not be recorded and was not applied",
                                    "code": "internal_error",
                                    "detail": {},
                                    "request_id": request_id_var.get(),
                                }
                            ).encode()
                            await send(
                                {
                                    "type": "http.response.start",
                                    "status": 500,
                                    "headers": [
                                        (b"content-type", b"application/json"),
                                        (b"content-length", str(len(body)).encode()),
                                    ],
                                }
                            )
                            await send({"type": "http.response.body", "body": body, "more_body": False})
                            return
                    else:
                        await run_in_threadpool(session.rollback)
            elif message["type"] == "http.response.body" and replaced:
                return  # the original body belongs to a response that was never acknowledged
            await send(message)

        await self.app(scope, receive, send_wrapper)
