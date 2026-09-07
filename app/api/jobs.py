"""Background jobs.

A small in-process worker pool backed by the ``jobs`` table. Long work — a
large ingestion, a heavy analysis — returns a task_id immediately and the
caller polls.

Its limits, stated rather than discovered: the queue lives in this process,
so a restart abandons anything RUNNING (those rows are marked FAILED at
startup rather than left lying), and jobs do not spread across replicas.
Swapping in Celery or RQ means replacing this module; the ``jobs`` table and
the API contract stay as they are.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.ids import new_task_id
from app.core.logging import get_logger, request_id_var
from app.database.enums import JobStatus
from app.database.models import Job
from app.database.session import session_scope

log = get_logger("jobs")

JobHandler = Callable[[str, dict], dict]


class JobRunner:
    def __init__(self, concurrency: int = 2):
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, concurrency), thread_name_prefix="ai-helper-job"
        )
        self._handlers: dict[str, JobHandler] = {}
        self._lock = threading.Lock()

    def register(self, kind: str, handler: JobHandler) -> None:
        with self._lock:
            self._handlers[kind] = handler

    def kinds(self) -> list[str]:
        return sorted(self._handlers)

    def submit(self, *, client_id: str, kind: str, payload: dict) -> str:
        if kind not in self._handlers:
            raise ValueError(f"no handler registered for job kind '{kind}'")
        job_id = new_task_id()
        with session_scope() as session:
            session.add(
                Job(
                    id=job_id,
                    client_id=client_id,
                    kind=kind,
                    status=JobStatus.QUEUED.value,
                    payload=payload,
                )
            )
        self._executor.submit(self._run, job_id, client_id, kind, payload)
        return job_id

    def _run(self, job_id: str, client_id: str, kind: str, payload: dict) -> None:
        request_id_var.set(job_id)
        with session_scope() as session:
            session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status=JobStatus.RUNNING.value, started_at=datetime.now(UTC))
            )
        try:
            result = self._handlers[kind](client_id, payload)
            status, error = JobStatus.SUCCEEDED, None
        except Exception as exc:
            result, status = {}, JobStatus.FAILED
            error = f"{type(exc).__name__}: {exc}"[:2000]
            log.error("job_failed", job_id=job_id, kind=kind, error=type(exc).__name__)
        with session_scope() as session:
            session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(
                    status=status.value,
                    result=result,
                    error=error,
                    progress=1.0 if status is JobStatus.SUCCEEDED else 0.0,
                    finished_at=datetime.now(UTC),
                )
            )
        log.info("job_finished", job_id=job_id, kind=kind, status=status.value)

    def recover_orphans(self) -> int:
        """Anything left RUNNING by a previous process is dead, not running."""
        with session_scope() as session:
            orphans = list(
                session.scalars(
                    select(Job).where(
                        Job.status.in_([JobStatus.RUNNING.value, JobStatus.QUEUED.value])
                    )
                )
            )
            for job in orphans:
                job.status = JobStatus.FAILED.value
                job.error = "abandoned: the worker process restarted before this job finished"
                job.finished_at = datetime.now(UTC)
        if orphans:
            log.warning("jobs_recovered", count=len(orphans))
        return len(orphans)

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting work.

        ``wait=True`` (the default) lets in-flight jobs finish writing their
        result rows before the process tears down its database engine. Without
        it a job thread can outlive the engine and either lose its result or
        write into whatever replaced it.
        """
        self._executor.shutdown(wait=wait, cancel_futures=not wait)
