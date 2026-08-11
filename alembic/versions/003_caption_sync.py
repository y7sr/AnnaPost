"""Track desired caption synchronization state.

Revision ID: 003
Revises: 002
"""

import sqlalchemy as sa
from sqlalchemy import inspect

import app.db.models  # noqa: F401 - registers mapped tables before reading metadata.
from alembic import op
from app.db.base import Base

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    # A pre-release Phase 2 run could stamp 002 after creating only accounts.
    # Complete the missing schema without touching configured account rows.
    missing = [table for name, table in Base.metadata.tables.items() if name not in existing]
    if missing:
        Base.metadata.create_all(bind, tables=missing)
    columns = {column["name"] for column in inspect(bind).get_columns("instagram_posts")}
    with op.batch_alter_table("instagram_posts") as batch:
        if "remote_caption_last_known" not in columns:
            batch.add_column(sa.Column("remote_caption_last_known", sa.Text(), nullable=True))
        if "caption_sync_status" not in columns:
            batch.add_column(
                sa.Column(
                    "caption_sync_status",
                    sa.String(length=32),
                    nullable=False,
                    server_default="in_sync",
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("instagram_posts") as batch:
        batch.drop_column("caption_sync_status")
        batch.drop_column("remote_caption_last_known")
