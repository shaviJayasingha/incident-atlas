"""Restrict rate-event cleanup to a fixed seven-day retention window.

Revision ID: 0004_bounded_rate_cleanup
Revises: 0003_approval_immutable
Create Date: 2026-11-22
"""

from alembic import op

revision = "0004_bounded_rate_cleanup"
down_revision = "0003_approval_immutable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION public.prune_expired_guest_rate_events() RETURNS bigint
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE deleted_count bigint;
        BEGIN
            DELETE FROM public.guest_rate_events
            WHERE occurred_at < pg_catalog.now() - interval '7 days';
            GET DIAGNOSTICS deleted_count = ROW_COUNT;
            RETURN deleted_count;
        END;
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.prune_expired_guest_rate_events() FROM PUBLIC"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION public.prune_expired_guest_rate_events()")
