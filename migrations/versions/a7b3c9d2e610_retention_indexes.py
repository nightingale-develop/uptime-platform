import sqlalchemy as sa
from alembic import op

revision = "a7b3c9d2e610"
down_revision = "92c7e8a31d40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_checks_checked_at", "checks", ["checked_at"])
    op.create_index(
        "ix_incidents_resolved_at",
        "incidents",
        ["resolved_at"],
        postgresql_where=sa.text("status = 'resolved'"),
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_resolved_at", table_name="incidents")
    op.drop_index("ix_checks_checked_at", table_name="checks")
