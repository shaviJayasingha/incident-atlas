"""Scope simulated approval uniqueness to a privacy-preserving visitor hash.

Revision ID: 0002_visitor_approval
Revises: 0001_initial
Create Date: 2026-11-22
"""

from alembic import op

revision = "0002_visitor_approval"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_investigation_mitigation_approval", "simulation_approvals", type_="unique"
    )
    op.drop_constraint("uq_replay_mitigation_approval", "simulation_approvals", type_="unique")
    op.create_unique_constraint(
        "uq_investigation_mitigation_approval",
        "simulation_approvals",
        ["investigation_id", "mitigation_id", "visitor_session_hash"],
    )
    op.create_unique_constraint(
        "uq_replay_mitigation_approval",
        "simulation_approvals",
        ["replay_report_id", "mitigation_id", "visitor_session_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_investigation_mitigation_approval", "simulation_approvals", type_="unique"
    )
    op.drop_constraint("uq_replay_mitigation_approval", "simulation_approvals", type_="unique")
    op.create_unique_constraint(
        "uq_investigation_mitigation_approval",
        "simulation_approvals",
        ["investigation_id", "mitigation_id"],
    )
    op.create_unique_constraint(
        "uq_replay_mitigation_approval",
        "simulation_approvals",
        ["replay_report_id", "mitigation_id"],
    )
