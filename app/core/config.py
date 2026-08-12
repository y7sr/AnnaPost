"""Application configuration using Pydantic Settings."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, ConfigDict, Field
from pydantic_settings import BaseSettings


# ``Settings`` reads ``.env`` for typed configuration, while credential
# references are resolved through ``os.environ``. Load the same file into the
# process environment without overriding explicitly exported variables.
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/annapost.db"

    # Durable media owned by AnnaPost. The database stores relative keys;
    # binaries stay outside SQLite and are never removed after publication.
    media_storage_dir: Path = Path("./data/media")
    media_max_size_bytes: int = 100 * 1024 * 1024

    # Logging
    log_level: str = "INFO"

    # Locking (see ARCHITECTURE.md §10 for why): how long a locked_at value
    # must age before a claim is considered stale and reclaimable by another
    # runner invocation.
    lock_stale_after_seconds: int = 600

    # Instagram Graph API. Versioning is centralized here; no client or
    # service may embed a Graph API version string.
    ig_graph_api_version: str = Field(
        default="v25.0",
        validation_alias=AliasChoices("INSTAGRAM_GRAPH_API_VERSION", "IG_GRAPH_API_VERSION"),
    )
    instagram_graph_base_url: str = Field(
        default="https://graph.instagram.com",
        validation_alias=AliasChoices("INSTAGRAM_GRAPH_BASE_URL", "IG_GRAPH_BASE_URL"),
    )

    # HTTP client timeouts (in seconds) for Instagram Graph API calls
    http_connect_timeout: float = 10.0
    http_read_timeout: float = 30.0
    http_write_timeout: float = 30.0
    http_pool_timeout: float = 10.0

    # Vend1r bridge. Both applications must receive the same non-empty token.
    vend1r_bridge_base_url: str = "http://127.0.0.1:8701"
    annapost_bridge_token: str | None = None
# Create settings instance
settings = Settings()

# Ensure data directory exists
Path("./data").mkdir(parents=True, exist_ok=True)
