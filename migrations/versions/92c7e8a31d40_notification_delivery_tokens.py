import sqlalchemy as sa
from alembic import op

revision = "92c7e8a31d40"
down_revision = "6a82b4d91f03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_deliveries", sa.Column("lease_token", sa.Uuid(), nullable=True)
    )
    op.create_check_constraint(
        "ck_notification_delivery_lease_expiry",
        "notification_deliveries",
        "lease_token IS NULL OR locked_until IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_notification_delivery_lease_expiry",
        "notification_deliveries",
        type_="check",
    )
    op.drop_column("notification_deliveries", "lease_token")
