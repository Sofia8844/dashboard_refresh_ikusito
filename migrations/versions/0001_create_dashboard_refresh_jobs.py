"""create dashboard refresh jobs

Revision ID: 0001_dashboard_refresh_jobs
Revises:
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_dashboard_refresh_jobs"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla de jobs y sus restricciones de idempotencia/concurrencia."""

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "dashboard_refresh_jobs",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=False),
        sa.Column("base_snapshot_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("result_snapshot_id", sa.Text(), nullable=True),
        sa.Column("updated_widgets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_widgets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed', 'skipped')",
            name="ck_dashboard_refresh_jobs_status",
        ),
    )
    op.create_index(
        "uq_dashboard_refresh_idempotency",
        "dashboard_refresh_jobs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_dashboard_refresh_active_page",
        "dashboard_refresh_jobs",
        ["project_id", "page_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )


def downgrade() -> None:
    """Elimina indices y tabla para revertir esta migracion."""

    op.drop_index("uq_dashboard_refresh_active_page", table_name="dashboard_refresh_jobs")
    op.drop_index("uq_dashboard_refresh_idempotency", table_name="dashboard_refresh_jobs")
    op.drop_table("dashboard_refresh_jobs")
