"""Baseline schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-07

This is a metadata baseline: it materialises the whole model layer as it
stands at v1.0. Every schema change AFTER this one must be a hand-reviewed
revision with an explicit upgrade and downgrade, and a note in
docs/CHANGELOG.md.
"""

from __future__ import annotations

from alembic import op

from app.database.models import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
