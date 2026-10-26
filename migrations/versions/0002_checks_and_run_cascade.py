"""Allowed values for lang and kind; deleting a chunking run deletes its chunks

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE articles ADD CONSTRAINT articles_lang_check CHECK (lang IN ('fr', 'en'))")
    op.execute(
        "ALTER TABLE articles ADD CONSTRAINT articles_kind_check "
        "CHECK (kind IN ('article', 'recital', 'annex'))"
    )
    op.execute("ALTER TABLE chunks ADD CONSTRAINT chunks_lang_check CHECK (lang IN ('fr', 'en'))")
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_run_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_run_id_fkey "
        "FOREIGN KEY (run_id) REFERENCES chunking_runs (id) ON DELETE CASCADE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_run_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_run_id_fkey "
        "FOREIGN KEY (run_id) REFERENCES chunking_runs (id)"
    )
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_lang_check")
    op.execute("ALTER TABLE articles DROP CONSTRAINT articles_kind_check")
    op.execute("ALTER TABLE articles DROP CONSTRAINT articles_lang_check")
