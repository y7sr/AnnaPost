"""Tests that exercise the actual Alembic migrations.

All test fixtures use the same migration path. These direct migration tests
also lock in the database-level invariants and downgrade behavior.

alembic/env.py reads the DB URL from app.core.config.settings rather than
from the Alembic Config object, so the settings singleton is patched (not
the Config) to point migrations at a throwaway per-test database file.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from app.core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return config


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point app.core.config.settings at a throwaway SQLite file for this test."""
    path = tmp_path / "migration_test.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{path}")
    return path


@pytest.fixture
def migrated_db(db_path: Path) -> Iterator[sqlite3.Connection]:
    command.upgrade(_alembic_config(), "head")
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


def test_upgrade_creates_all_core_tables(migrated_db: sqlite3.Connection) -> None:
    tables = {
        row[0] for row in migrated_db.execute("select name from sqlite_master where type='table'")
    }
    expected = {
        "instagram_accounts",
        "instagram_posts",
        "instagram_post_metrics",
        "instagram_comments",
        "instagram_jobs",
        "instagram_events",
        "global_options",
    }
    assert expected <= tables


def test_only_one_default_account_allowed(migrated_db: sqlite3.Connection) -> None:
    migrated_db.execute(
        "insert into instagram_accounts (name, is_default, enabled) values ('a', 1, 1)"
    )
    migrated_db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(
            "insert into instagram_accounts (name, is_default, enabled) values ('b', 1, 1)"
        )

    # Multiple non-default accounts remain unrestricted.
    migrated_db.execute(
        "insert into instagram_accounts (name, is_default, enabled) values ('c', 0, 1)"
    )
    migrated_db.commit()


def test_duplicate_instagram_comment_id_rejected(migrated_db: sqlite3.Connection) -> None:
    migrated_db.execute(
        "insert into instagram_accounts (name, is_default, enabled) values ('a', 1, 1)"
    )
    migrated_db.execute(
        "insert into instagram_posts (account_id, media_type, media_source_type, media_source, status) "
        "values (1, 'image', 'url', 'https://example.com/x.jpg', 'draft')"
    )
    migrated_db.execute(
        "insert into instagram_comments (account_id, post_id, instagram_comment_id) "
        "values (1, 1, 'ig_comment_1')"
    )
    migrated_db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(
            "insert into instagram_comments (account_id, post_id, instagram_comment_id) "
            "values (1, 1, 'ig_comment_1')"
        )


def test_events_survive_parent_deletion_with_references_cleared(
    migrated_db: sqlite3.Connection,
) -> None:
    """Append-only history must follow the migration's SET NULL policy."""
    migrated_db.execute("pragma foreign_keys=on")
    migrated_db.execute(
        "insert into instagram_accounts (name, is_default, enabled) values ('a', 1, 1)"
    )
    migrated_db.execute(
        "insert into instagram_posts (account_id, media_type, media_source_type, media_source, status) "
        "values (1, 'image', 'url', 'https://example.com/x.jpg', 'published')"
    )
    migrated_db.execute(
        "insert into instagram_events (account_id, post_id, event_type) "
        "values (1, 1, 'publish_succeeded')"
    )
    migrated_db.execute("delete from instagram_posts where id = 1")
    migrated_db.commit()

    event = migrated_db.execute("select account_id, post_id from instagram_events").fetchone()
    assert event == (1, None)


def test_downgrade_then_upgrade_round_trips(db_path: Path) -> None:
    """The migration's downgrade() must not corrupt Alembic's own bookkeeping."""
    config = _alembic_config()

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
    conn.close()
    assert "instagram_accounts" in tables
