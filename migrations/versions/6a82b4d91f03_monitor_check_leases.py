"""Add expiring monitor check leases.

Revision ID: 6a82b4d91f03
Revises: 18e7e0bc5755
"""

import sqlalchemy as sa
from alembic import op

revision = "6a82b4d91f03"
down_revision = "18e7e0bc5755"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("monitors", sa.Column("check_lease_token", sa.Uuid(), nullable=True))
    op.add_column(
        "monitors",
        sa.Column("check_lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_monitors_check_lease_pair",
        "monitors",
        "(check_lease_token IS NULL) = (check_lease_until IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_monitors_check_lease_pair", "monitors", type_="check")
    op.drop_column("monitors", "check_lease_until")
    op.drop_column("monitors", "check_lease_token")
