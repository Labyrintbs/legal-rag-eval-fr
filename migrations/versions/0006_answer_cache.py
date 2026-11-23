"""The answer cache (step 0f, decision 4): finished replies by question, and the trace link to the entry that served them

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

OUTCOMES = (
    "answered", "refused_weak_retrieval", "refused_by_model", "invalid_citation",
    "parse_error", "llm_error", "rate_limited", "llm_disabled",
)


def outcome_check(outcomes: tuple[str, ...]) -> str:
    return "CHECK (outcome IN (" + ", ".join(f"'{o}'" for o in outcomes) + "))"


def upgrade() -> None:
    # Only a hash of the question is stored: a visitor may type personal data.
    op.execute(
        """
        CREATE TABLE answer_cache (
            key text PRIMARY KEY,
            reply jsonb NOT NULL,
            outcome text NOT NULL CHECK (outcome IN ('answered', 'refused_by_model')),
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            hits integer NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX answer_cache_expires ON answer_cache (expires_at)")
    op.execute("ALTER TABLE query_traces ADD COLUMN cache_key text")
    op.execute("ALTER TABLE query_traces DROP CONSTRAINT query_traces_outcome_check")
    op.execute(f"ALTER TABLE query_traces ADD CONSTRAINT query_traces_outcome_check {outcome_check((*OUTCOMES, 'cache_hit'))}")


def downgrade() -> None:
    op.execute("DELETE FROM query_traces WHERE outcome = 'cache_hit'")
    op.execute("ALTER TABLE query_traces DROP CONSTRAINT query_traces_outcome_check")
    op.execute(f"ALTER TABLE query_traces ADD CONSTRAINT query_traces_outcome_check {outcome_check(OUTCOMES)}")
    op.execute("ALTER TABLE query_traces DROP COLUMN cache_key")
    op.execute("DROP TABLE answer_cache")
