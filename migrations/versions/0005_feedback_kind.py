"""Kind of problem a visitor reports with a thumbs-down (step 0f, decision 5)

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

KINDS = ("wrong_answer", "wrong_citation", "missing_article", "other")


def upgrade() -> None:
    kinds = ", ".join(f"'{k}'" for k in KINDS)
    op.execute(f"ALTER TABLE query_traces ADD COLUMN feedback_kind text CHECK (feedback_kind IN ({kinds}))")


def downgrade() -> None:
    op.execute("ALTER TABLE query_traces DROP COLUMN feedback_kind")
