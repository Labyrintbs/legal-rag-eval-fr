"""Erasing the text of ordinary requests after 7 days (step 0f, privacy)

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # An erased row keeps its outcome, scores and cited articles, but no text and no hash of the text: the hash goes too.
    op.execute("ALTER TABLE query_traces ALTER COLUMN question_sha256 DROP NOT NULL")
    op.execute("ALTER TABLE query_traces ADD COLUMN erased_at timestamptz")  # when the text was erased
    op.execute("ALTER TABLE query_traces ADD COLUMN feedback_at timestamptz")  # when the vote came: to size the 7-day window


def downgrade() -> None:
    op.execute("UPDATE query_traces SET question_sha256 = '' WHERE question_sha256 IS NULL")
    op.execute("ALTER TABLE query_traces ALTER COLUMN question_sha256 SET NOT NULL")
    op.execute("ALTER TABLE query_traces DROP COLUMN feedback_at")
    op.execute("ALTER TABLE query_traces DROP COLUMN erased_at")
