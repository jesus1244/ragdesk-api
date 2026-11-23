"""create conversation and message tables

Revision ID: 2a18ded32adc
Revises: 71f7f2b6941b
Create Date: 2026-11-23 10:45:15.229854

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2a18ded32adc"
down_revision: str | Sequence[str] | None = "71f7f2b6941b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversation",
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("visitor_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bot.id"], name=op.f("conversation_bot_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("conversation_pkey")),
    )
    op.create_index(op.f("conversation_bot_id_idx"), "conversation", ["bot_id"], unique=False)
    op.create_table(
        "message",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("answered", sa.Boolean(), nullable=True),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bot.id"], name=op.f("message_bot_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("message_conversation_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("message_pkey")),
    )
    op.create_index(
        "message_bot_id_created_at_idx", "message", ["bot_id", "created_at"], unique=False
    )
    op.create_index(
        op.f("message_conversation_id_idx"), "message", ["conversation_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("message_conversation_id_idx"), table_name="message")
    op.drop_index("message_bot_id_created_at_idx", table_name="message")
    op.drop_table("message")
    op.drop_index(op.f("conversation_bot_id_idx"), table_name="conversation")
    op.drop_table("conversation")
