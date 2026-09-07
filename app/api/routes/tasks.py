"""Async tasks: submit long work, poll for the result."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_client, db_dep
from app.api.schemas import TaskCreated, TaskRequest, TaskStatus
from app.core.errors import NotFoundError
from app.database.models import Client, Job

router = APIRouter(prefix="/api/v1", tags=["tasks"])

CHAT_JOB = "chat"


@router.post("/tasks", response_model=TaskCreated, status_code=202, summary="Queue a task")
def create_task(
    body: TaskRequest,
    request: Request,
    client: Client = Depends(current_client),
) -> TaskCreated:
    payload = body.model_dump()
    job_id = request.app.state.jobs.submit(
        client_id=client.client_id, kind=CHAT_JOB, payload=payload
    )
    return TaskCreated(task_id=job_id, status="queued", kind=CHAT_JOB)


@router.get("/tasks/{task_id}", response_model=TaskStatus, summary="Check a task")
def get_task(
    task_id: str,
    client: Client = Depends(current_client),
    db: Session = Depends(db_dep),
) -> TaskStatus:
    job = db.get(Job, task_id)
    # Not-found and not-yours are the same answer, so task ids cannot be probed.
    if job is None or job.client_id != client.client_id:
        raise NotFoundError(f"task '{task_id}' not found")
    return TaskStatus(
        task_id=job.id,
        kind=job.kind,
        status=job.status,
        progress=job.progress,
        result=job.result or None,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/tasks", response_model=list[TaskStatus], summary="List this client's tasks")
def list_tasks(
    limit: int = 50,
    client: Client = Depends(current_client),
    db: Session = Depends(db_dep),
) -> list[TaskStatus]:
    jobs = db.scalars(
        select(Job)
        .where(Job.client_id == client.client_id)
        .order_by(Job.created_at.desc())
        .limit(min(limit, 200))
    )
    return [
        TaskStatus(
            task_id=job.id,
            kind=job.kind,
            status=job.status,
            progress=job.progress,
            result=job.result or None,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job in jobs
    ]
