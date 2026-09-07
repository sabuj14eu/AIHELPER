"""Identifier helpers. Every request gets one, and it appears in every record."""

from __future__ import annotations

import uuid


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def new_task_id() -> str:
    return f"task_{uuid.uuid4().hex}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
