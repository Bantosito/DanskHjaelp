"""Learning core and materials tables.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("lemma", sa.String(200), nullable=False),
        sa.Column("part_of_speech", sa.String(30), nullable=False),
        sa.Column("gender", sa.String(2)),
        sa.Column("forms", JSONB, nullable=False),
        sa.Column("forms_display", sa.Text, nullable=False),
        sa.Column("meaning_da", sa.Text, nullable=False),
        sa.Column("meaning_en", sa.Text, nullable=False),
        sa.Column("example", sa.Text, nullable=False),
        sa.Column("confusables", sa.Text),
        sa.Column("explanation_en", sa.Text),
        sa.Column("uncertain", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="set"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("lemma", "part_of_speech"),
    )
    # Finds a word from any of its forms: "stort" finds "stor".
    op.create_index(
        "ix_items_forms",
        "items",
        ["forms"],
        postgresql_using="gin",
        postgresql_ops={"forms": "jsonb_path_ops"},
    )

    op.create_table(
        "lookups",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("query", sa.String(300), nullable=False),
        sa.Column("context_sentence", sa.Text),
        sa.Column("direction", sa.String(5), nullable=False),
        sa.Column("used_english", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_lookups_query", "lookups", ["query"])
    op.create_index("ix_lookups_item_id", "lookups", ["item_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("file_path", sa.Text),
        sa.Column("source", sa.Text),
        sa.Column("tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer),
        sa.Column("text", sa.Text, nullable=False),
    )
    op.create_table(
        "item_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "document_id",
            sa.Integer,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_id", sa.Integer, sa.ForeignKey("chunks.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    for table in ("item_sources", "chunks", "documents", "lookups", "items"):
        op.drop_table(table)
