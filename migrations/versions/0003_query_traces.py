"""One row per request to the service: the question, what retrieval and the model did, the outcome, the cost

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OUTCOMES = (
    "answered", "refused_weak_retrieval", "refused_by_model", "invalid_citation",
    "parse_error", "llm_error", "rate_limited", "llm_disabled",
)


def upgrade() -> None:
    outcomes = ", ".join(f"'{o}'" for o in OUTCOMES)
    op.execute(
        f"""
        CREATE TABLE query_traces (
            id bigserial PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            -- questions can hold personal data: rows are purged after 30 days (D13)
            expires_at timestamptz NOT NULL DEFAULT now() + interval '30 days',
            request_id text NOT NULL,
            lang text NOT NULL CHECK (lang IN ('fr', 'en')),
            question text NOT NULL,
            question_sha256 text NOT NULL,
            client_hash text,
            mode text NOT NULL CHECK (mode IN ('answer', 'search')),
            outcome text NOT NULL CHECK (outcome IN ({outcomes})),
            refusal_reason text,
            error text,
            retrieved jsonb NOT NULL DEFAULT '[]',
            top_score real,
            score_gap real,
            cited jsonb NOT NULL DEFAULT '[]',
            answer text,
            model text,
            prompt_id text,
            tokens_in integer,
            tokens_out integer,
            tokens_cached integer,
            cost_usd numeric(10, 6),
            retrieval_ms integer,
            llm_ms integer,
            total_ms integer,
            code_version text,
            data_version text,
            feedback smallint CHECK (feedback IN (-1, 1)),
            feedback_comment text
        )
        """
    )
    op.execute("CREATE INDEX query_traces_created ON query_traces (created_at)")
    op.execute("CREATE INDEX query_traces_outcome ON query_traces (outcome, created_at)")
    op.execute("CREATE INDEX query_traces_expires ON query_traces (expires_at)")
    op.execute("CREATE UNIQUE INDEX query_traces_request ON query_traces (request_id)")


def downgrade() -> None:
    op.execute("DROP TABLE query_traces")
