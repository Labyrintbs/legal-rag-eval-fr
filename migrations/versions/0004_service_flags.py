"""Switches of the running service, changed by a command without a restart (step 0d, decision 13)

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE service_flags (
            name text PRIMARY KEY,
            value boolean NOT NULL,
            changed_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("INSERT INTO service_flags (name, value) VALUES ('llm_enabled', true)")


def downgrade() -> None:
    op.execute("DROP TABLE service_flags")
