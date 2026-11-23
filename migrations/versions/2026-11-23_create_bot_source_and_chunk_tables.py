"""create bot, source and chunk tables

Revision ID: 71f7f2b6941b
Revises: 2f249b5ff93b
Create Date: 2026-11-23 10:34:21.286867

"""

from typing import Sequence

import pgvector.sqlalchemy.vector
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "71f7f2b6941b"
down_revision: str | Sequence[str] | None = "2f249b5ff93b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "bot",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("public_key", sa.String(length=64), nullable=False),
        sa.Column("welcome_message", sa.String(length=300), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("allowed_origins", sa.ARRAY(sa.String(length=255)), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["auth_user.id"], name=op.f("bot_owner_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("bot_pkey")),
        sa.UniqueConstraint("public_key", name=op.f("bot_public_key_key")),
    )
    op.create_index(op.f("bot_owner_id_idx"), "bot", ["owner_id"], unique=False)
    op.create_table(
        "source",
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("raw", sa.LargeBinary(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bot.id"], name=op.f("source_bot_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("source_pkey")),
    )
    op.create_index(op.f("source_bot_id_idx"), "source", ["bot_id"], unique=False)
    op.create_table(
        "chunk",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=False),
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', title || ' ' || content)", persisted=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bot.id"], name=op.f("chunk_bot_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source.id"], name=op.f("chunk_source_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("chunk_pkey")),
    )
    op.create_index(op.f("chunk_bot_id_idx"), "chunk", ["bot_id"], unique=False)
    op.create_index(
        "chunk_embedding_hnsw_idx",
        "chunk",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "chunk_search_gin_idx", "chunk", ["search"], unique=False, postgresql_using="gin"
    )
    op.create_index(op.f("chunk_source_id_idx"), "chunk", ["source_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("chunk_source_id_idx"), table_name="chunk")
    op.drop_index("chunk_search_gin_idx", table_name="chunk", postgresql_using="gin")
    op.drop_index(
        "chunk_embedding_hnsw_idx",
        table_name="chunk",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(op.f("chunk_bot_id_idx"), table_name="chunk")
    op.drop_table("chunk")
    op.drop_index(op.f("source_bot_id_idx"), table_name="source")
    op.drop_table("source")
    op.drop_index(op.f("bot_owner_id_idx"), table_name="bot")
    op.drop_table("bot")
    op.execute("DROP EXTENSION IF EXISTS vector")
