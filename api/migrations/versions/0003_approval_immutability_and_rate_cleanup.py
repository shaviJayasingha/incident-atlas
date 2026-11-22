"""Make approval records append-only and index rate-event retention cleanup.

Revision ID: 0003_approval_immutable
Revises: 0002_visitor_approval
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_approval_immutable"
down_revision = "0002_visitor_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_guest_rate_occurred_at", "guest_rate_events", ["occurred_at"], unique=False
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION reject_simulation_approval_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'simulation approvals are append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER simulation_approvals_append_only
            BEFORE UPDATE OR DELETE ON simulation_approvals
            FOR EACH ROW EXECUTE FUNCTION reject_simulation_approval_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER simulation_approvals_append_only ON simulation_approvals"))
    op.execute(sa.text("DROP FUNCTION reject_simulation_approval_mutation()"))
    op.drop_index("ix_guest_rate_occurred_at", table_name="guest_rate_events")
