"""Full schema migration for Phase 2.

This migration creates all 7 core tables:
- instagram_accounts
- instagram_posts
- instagram_post_metrics
- instagram_comments
- instagram_jobs
- instagram_events
- global_options

Revision ID: 002
Revises: 001
Create Date: 2026-08-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema to create all core tables."""

    # Create instagram_accounts table
    op.create_table(
        "instagram_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("instagram_user_id", sa.String(length=255), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, default=False, server_default=sa.text("0")
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, default=True, server_default=sa.text("1")
        ),
        sa.Column("access_token_ref", sa.String(length=500), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
            onupdate=sa.func.datetime("now"),
        ),
        sa.Column("last_successful_api_call_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Partial unique index: only one account may have is_default=True.
    op.create_index(
        "ux_instagram_accounts_is_default",
        "instagram_accounts",
        ["is_default"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
    )

    # Create instagram_posts table
    op.create_table(
        "instagram_posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column(
            "media_type", sa.Enum("image", "carousel", "reel", name="postmediatype"), nullable=False
        ),
        sa.Column(
            "media_source_type",
            sa.Enum("url", "local_file", "object_storage", name="postmediasourcetype"),
            nullable=False,
        ),
        sa.Column("media_source", sa.String(length=2048), nullable=False),
        sa.Column("media_payload_json", sqlite.JSON(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "ready",
                "scheduled",
                "publishing",
                "published",
                "failed",
                "delete_requested",
                "deleted",
                "canceled",
                name="poststatus",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("instagram_media_id", sa.String(length=255), nullable=True),
        sa.Column("instagram_container_id", sa.String(length=255), nullable=True),
        sa.Column("instagram_permalink", sa.String(length=2048), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "soft_deleted", sa.Boolean(), nullable=False, default=False, server_default=sa.text("0")
        ),
        sa.Column("delete_requested_at", sa.DateTime(), nullable=True),
        sa.Column(
            "publish_attempt_count",
            sa.Integer(),
            nullable=False,
            default=0,
            server_default=sa.text("0"),
        ),
        sa.Column("last_publish_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("next_sync_at", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
            onupdate=sa.func.datetime("now"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("idempotency_key"),
        sa.Index("ix_instagram_posts_status", "status"),
        sa.Index("ix_instagram_posts_scheduled_at", "scheduled_at"),
        sa.Index("ix_instagram_posts_next_sync_at", "next_sync_at"),
        sa.Index("ix_instagram_posts_account_status", "account_id", "status"),
        sa.Index("ix_instagram_posts_locked_at", "locked_at"),
    )

    # Create instagram_post_metrics table
    op.create_table(
        "instagram_post_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
        ),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("reach", sa.Integer(), nullable=True),
        sa.Column("plays", sa.Integer(), nullable=True),
        sa.Column("avg_watch_time_ms", sa.Integer(), nullable=True),
        sa.Column("total_watch_time_ms", sa.Integer(), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("saved", sa.Integer(), nullable=True),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("total_interactions", sa.Integer(), nullable=True),
        sa.Column("profile_activity", sa.Integer(), nullable=True),
        sa.Column("follows", sa.Integer(), nullable=True),
        sa.Column("raw_metrics_json", sqlite.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["post_id"], ["instagram_posts.id"], ondelete="CASCADE"),
        sa.Index("ix_instagram_post_metrics_post_captured", "post_id", "captured_at"),
        sa.Index("ix_instagram_post_metrics_captured", "captured_at"),
    )

    # Create instagram_comments table
    op.create_table(
        "instagram_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("instagram_comment_id", sa.String(length=255), nullable=False),
        sa.Column("parent_instagram_comment_id", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("instagram_user_id_if_available", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("created_at_remote", sa.DateTime(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
            onupdate=sa.func.datetime("now"),
        ),
        sa.Column("like_count_if_available", sa.Integer(), nullable=True),
        sa.Column(
            "is_reply", sa.Boolean(), nullable=False, default=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_hidden", sa.Boolean(), nullable=False, default=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_deleted_remote",
            sa.Boolean(),
            nullable=False,
            default=False,
            server_default=sa.text("0"),
        ),
        sa.Column("raw_json", sqlite.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["instagram_posts.id"], ondelete="CASCADE"),
        sa.Index("ix_instagram_comments_instagram_id", "instagram_comment_id", unique=True),
        sa.Index("ix_instagram_comments_post", "post_id"),
        sa.Index("ix_instagram_comments_account_post", "account_id", "post_id"),
        sa.Index("ix_instagram_comments_parent", "parent_instagram_comment_id"),
        sa.Index("ix_instagram_comments_deleted", "is_deleted_remote"),
    )

    # Create instagram_jobs table
    op.create_table(
        "instagram_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "job_type",
            sa.Enum("publish", "delete_post", "create_comment", "reply_comment", name="jobtype"),
            nullable=False,
        ),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("comment_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sqlite.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", "canceled", name="jobstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, default=0, server_default=sa.text("0")),
        sa.Column(
            "max_attempts", sa.Integer(), nullable=False, default=3, server_default=sa.text("3")
        ),
        sa.Column("run_after", sa.DateTime(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["instagram_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["comment_id"], ["instagram_comments.id"], ondelete="CASCADE"),
        sa.Index("ix_instagram_jobs_job_type", "job_type"),
        sa.Index("ix_instagram_jobs_status_run_after", "status", "run_after"),
        sa.Index("ix_instagram_jobs_locked_at", "locked_at"),
        sa.Index("ix_instagram_jobs_created", "created_at"),
    )

    # Create instagram_events table
    op.create_table(
        "instagram_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum(
                "post_created",
                "post_updated",
                "post_scheduled",
                "publish_started",
                "publish_succeeded",
                "publish_failed",
                "sync_started",
                "sync_succeeded",
                "sync_failed",
                "metric_snapshot_created",
                "delete_requested",
                "delete_started",
                "delete_succeeded",
                "delete_failed",
                "comment_received",
                "comment_queued",
                "comment_sent",
                "comment_failed",
                name="eventtype",
            ),
            nullable=False,
        ),
        sa.Column("payload_json", sqlite.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
            index=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["instagram_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["post_id"], ["instagram_posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["instagram_jobs.id"], ondelete="SET NULL"),
        sa.Index("ix_instagram_events_account_id", "account_id"),
        sa.Index("ix_instagram_events_post_id", "post_id"),
        sa.Index("ix_instagram_events_job_id", "job_id"),
        sa.Index("ix_instagram_events_account_created", "account_id", "created_at"),
        sa.Index("ix_instagram_events_post_created", "post_id", "created_at"),
        sa.Index("ix_instagram_events_job_created", "job_id", "created_at"),
    )

    # Create global_options table
    op.create_table(
        "global_options",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value_json", sqlite.JSON(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.datetime("now"),
            onupdate=sa.func.datetime("now"),
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Downgrade database schema by dropping all core tables."""
    op.drop_table("global_options")
    op.drop_table("instagram_events")
    op.drop_table("instagram_jobs")
    op.drop_table("instagram_comments")
    op.drop_table("instagram_post_metrics")
    op.drop_table("instagram_posts")
    op.drop_index("ux_instagram_accounts_is_default", table_name="instagram_accounts")
    op.drop_table("instagram_accounts")
