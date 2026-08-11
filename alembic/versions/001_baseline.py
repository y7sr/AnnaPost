"""Baseline migration.

This is the first migration that sets up the basis for future migrations.
It doesn't create any application tables - those will come in Phase 2.
This just proves the migration pipeline works end-to-end.

Revision ID: 001
Revises:
Create Date: 2026-08-11 00:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Baseline migration - no tables to create yet
    # This proves the migration pipeline works
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    # Baseline migration - nothing to downgrade
    pass
