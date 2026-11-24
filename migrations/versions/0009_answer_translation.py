"""The English translation of an answer, stored with the cached answer (step 0f, part 4)

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A translation is a model call that costs money: its trace row has the mode "translate", which no limit counts as an answer.
    op.execute("ALTER TABLE query_traces DROP CONSTRAINT query_traces_mode_check")
    op.execute("ALTER TABLE query_traces ADD CONSTRAINT query_traces_mode_check CHECK (mode IN ('answer', 'search', 'translate'))")
    op.execute("ALTER TABLE answer_cache ADD COLUMN answer_en text")


def downgrade() -> None:
    op.execute("DELETE FROM query_traces WHERE mode = 'translate'")
    op.execute("ALTER TABLE query_traces DROP CONSTRAINT query_traces_mode_check")
    op.execute("ALTER TABLE query_traces ADD CONSTRAINT query_traces_mode_check CHECK (mode IN ('answer', 'search'))")
    op.execute("ALTER TABLE answer_cache DROP COLUMN answer_en")
