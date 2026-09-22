from alembic import op

revision = "b8d4e2f60173"
down_revision = "a7b3c9d2e610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_destination_type ADD VALUE 'slack'")


def downgrade() -> None:
    op.execute("LOCK TABLE notification_destinations IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM notification_destinations
                WHERE destination_type::text = 'slack'
            ) THEN
                RAISE EXCEPTION 'Remove Slack destinations before downgrading';
            END IF;
        END $$
    """)
    op.execute(
        "ALTER TYPE notification_destination_type RENAME TO notification_destination_type_old"
    )
    op.execute(
        "CREATE TYPE notification_destination_type AS ENUM ('webhook', 'telegram', 'email')"
    )
    op.execute("""
        ALTER TABLE notification_destinations ALTER COLUMN destination_type
        TYPE notification_destination_type
        USING destination_type::text::notification_destination_type
    """)
    op.execute("DROP TYPE notification_destination_type_old")
