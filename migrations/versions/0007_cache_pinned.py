"""Pinned cache entries: the example questions of the demo (step 0f, decision 4)

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A pinned entry does not expire and a thumbs-down does not remove it: the examples are what the user checked by hand.
    op.execute("ALTER TABLE answer_cache ADD COLUMN pinned boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("UPDATE answer_cache SET expires_at = now() WHERE pinned")
    op.execute("ALTER TABLE answer_cache DROP COLUMN pinned")
