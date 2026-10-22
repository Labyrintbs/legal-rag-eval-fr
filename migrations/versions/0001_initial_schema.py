"""Initial schema: corpus versions, articles, chunking runs, chunks, chunk embeddings

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE corpus_versions (
            id serial PRIMARY KEY,
            source_key text NOT NULL,
            source_name text NOT NULL,
            source_url text NOT NULL,
            snapshot_date date,
            retrieved_at timestamptz NOT NULL,
            file_sha256 text NOT NULL,
            row_count integer NOT NULL,
            license text NOT NULL,
            notes text,
            UNIQUE (source_key, file_sha256)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE articles (
            uid text PRIMARY KEY,
            corpus_version_id integer NOT NULL REFERENCES corpus_versions (id),
            source_code text NOT NULL,
            lang text NOT NULL,
            kind text NOT NULL,
            native_id text NOT NULL,
            article_num text NOT NULL,
            title text,
            section_path text NOT NULL,
            body_text text NOT NULL,
            valid_from date,
            valid_to date,
            status text,
            content_hash text NOT NULL,
            source_url text NOT NULL,
            extra jsonb NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("CREATE INDEX articles_lookup ON articles (source_code, lang, article_num)")
    op.execute(
        """
        CREATE TABLE chunking_runs (
            id serial PRIMARY KEY,
            name text NOT NULL UNIQUE,
            header_style text NOT NULL,
            header_k integer,
            max_tokens integer NOT NULL,
            split_rule text NOT NULL,
            tokenizer text NOT NULL,
            code_version text NOT NULL,
            params jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # tsv picks the dictionary from lang; the CASE keeps the expression immutable (tested).
    op.execute(
        """
        CREATE TABLE chunks (
            id bigserial PRIMARY KEY,
            run_id integer NOT NULL REFERENCES chunking_runs (id),
            article_uid text NOT NULL REFERENCES articles (uid),
            chunk_index integer NOT NULL,
            lang text NOT NULL,
            header_text text NOT NULL,
            body_text text NOT NULL,
            embed_text text NOT NULL,
            embed_text_hash text NOT NULL,
            token_count integer NOT NULL,
            extra jsonb NOT NULL DEFAULT '{}',
            tsv tsvector GENERATED ALWAYS AS (
                CASE WHEN lang = 'fr' THEN to_tsvector('french', embed_text)
                     ELSE to_tsvector('english', embed_text) END
            ) STORED,
            UNIQUE (run_id, article_uid, chunk_index)
        )
        """
    )
    op.execute("CREATE INDEX chunks_article ON chunks (article_uid)")
    op.execute("CREATE INDEX chunks_tsv ON chunks USING gin (tsv)")
    op.execute(
        """
        CREATE TABLE chunk_embeddings (
            chunk_id bigint NOT NULL REFERENCES chunks (id) ON DELETE CASCADE,
            model text NOT NULL,
            model_revision text NOT NULL,
            dim integer NOT NULL,
            embedding vector(1024) NOT NULL,
            embed_text_hash text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (chunk_id, model)
        )
        """
    )
    # The HNSW index is built after the vectors are loaded: see legalrag.store.build_hnsw_index.


def downgrade() -> None:
    for table in ("chunk_embeddings", "chunks", "chunking_runs", "articles", "corpus_versions"):
        op.execute(f"DROP TABLE {table}")
