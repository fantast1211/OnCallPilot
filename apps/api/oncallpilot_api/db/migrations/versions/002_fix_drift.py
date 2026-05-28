"""Fix drift: add missing columns and tables.

Revision ID: 002_fix_drift
Revises: 001_initial
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "002_fix_drift"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- tool_calls: add step_index, started_at, ended_at, latency_ms, error_message --
    op.add_column("tool_calls", sa.Column("step_index", sa.Integer(), nullable=True))
    op.add_column("tool_calls", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tool_calls", sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tool_calls", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column("tool_calls", sa.Column("error_message", sa.Text(), nullable=True))

    # -- investigation_sessions: add job_id for arq idempotency --
    op.add_column("investigation_sessions", sa.Column("job_id", sa.String(256), nullable=True))

    # -- incidents: add closed_at, closed_reason, reopen_count, last_seen_at --
    op.add_column("incidents", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("incidents", sa.Column("closed_reason", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("reopen_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("incidents", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))

    # -- datasource_status table (ORM has DatasourceStatus model) --
    op.create_table(
        "datasource_status",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(256), nullable=False, unique=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("datasource_status")
    op.drop_column("incidents", "last_seen_at")
    op.drop_column("incidents", "reopen_count")
    op.drop_column("incidents", "closed_reason")
    op.drop_column("incidents", "closed_at")
    op.drop_column("investigation_sessions", "job_id")
    op.drop_column("tool_calls", "error_message")
    op.drop_column("tool_calls", "latency_ms")
    op.drop_column("tool_calls", "ended_at")
    op.drop_column("tool_calls", "started_at")
    op.drop_column("tool_calls", "step_index")
