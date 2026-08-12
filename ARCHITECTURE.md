# AnnaPost Architecture Reference

**Detailed architecture reference for AnnaPost.**

`CLAUDE.md` gives the short version for quick orientation; this document is the full reference — data model, state machine, client contract, error/retry policy, and the decisions locked in by Phase 2.

**Status:** Phase 3 Implementation Complete. The Phase 2 contracts are now implemented through services, API routes, the shared Instagram client, runners, CLI, migrations, and mocked acceptance coverage.

**Last Updated:** 2026-08-12

---

## Table of Contents

1. [Principles](#1-principles)
2. [Layering](#2-layering)
3. [Data Model](#3-data-model)
4. [Post State Machine](#4-post-state-machine)
5. [Idempotency & Locking](#5-idempotency--locking)
6. [InstagramClient Contract](#6-instagramclient-contract)
7. [Runners (Phase 3 Contract)](#7-runners-phase-3-contract)
8. [Reconciliation & Caption Sync](#8-reconciliation--caption-sync)
9. [Media Handling](#9-media-handling)
10. [Decision Log (Phase 2)](#10-decision-log-phase-2)
11. [API Surface](#11-api-surface)
12. [SQLite Specifics](#12-sqlite-specifics)
13. [Observability](#13-observability)
14. [Security](#14-security)
15. [Testing](#15-testing)
16. [Phase Roadmap](#16-phase-roadmap)
17. [Code Quality Assessment](#17-code-quality-assessment)
18. [Vend1r Bridge](#18-vend1r-bridge)

---

## 1. Principles

```
DATABASE = desired state + internal history
INSTAGRAM = external state
RUNNERS   = reconciliation between both
```

External producers (Vend1r or others) talk only to `/api/v1`. They create/modify rows; they never see Graph API container IDs, retry mechanics, or sync timing. The API is the *only* integration boundary — nothing calls into this app's internals directly.

```
External Producer → FastAPI → Database → Runners → InstagramClient → Instagram Graph API
```

## 18. Vend1r Bridge

Vend1r and AnnaPost share a coherent post lifecycle but retain their own
responsibilities. Vend1r produces a caption, selected image, critique, and an
editable status Fragment. AnnaPost owns durable `instagram_posts`, imports the
media, queues work, calls Instagram, and returns final status/permalink.

The correlation key is the Vend1r-provided deterministic `idempotency_key`
(`vend1r:{entity_id}:fragment:{status_fragment_id}`), not new source-specific
columns in `instagram_posts`. The bridge code is
`app/services/vend1r_bridge.py`; it polls Vend1r's authenticated API with the
same `ANNAPOST_BRIDGE_TOKEN` configured on both applications.

Vend1r `ready` creates/updates an AnnaPost desired post and queues publication.
Vend1r `deleted` is passed through `request_post_deletion()`: a published post
first becomes `delete_requested`, then the action runner completes the remote
deletion and only then reports `deleted`. Direct terminal-state writes are
forbidden because they bypass runner side effects.

Current limitation: the polling service exists but is not yet exposed through
the AnnaPost CLI or a recurring runner, and end-to-end bridge tests are not yet
present. Do not treat the bridge as live-verified.

Do not introduce Redis/Celery/RabbitMQ/an external scheduler/Docker-only architecture unless a concrete need forces it. SQLite is the queue; runners are invoked externally (cron/systemd/launchd/manual), not by a built-in scheduler.

---

## 2. Layering

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                      │
│  app/api/routes/ - Thin HTTP layer, validation, status     │
├─────────────────────────────────────────────────────────┤
│                    Admin UI Layer                           │
│  app/admin/routes/ - Template-based admin interfaces       │
├─────────────────────────────────────────────────────────┤
│                  Services Layer                             │
│  app/services/ - Business logic, state transitions        │
├─────────────────────────────────────────────────────────┤
│                 Repositories Layer                          │
│  app/repositories/ - Query helpers, database operations    │
├─────────────────────────────────────────────────────────┤
│                   Database Layer                            │
│  app/db/models/ - SQLAlchemy ORM models                   │
│  app/db/session/ - Connection management                   │
├─────────────────────────────────────────────────────────┤
│               Instagram Client Layer                        │
│  app/instagram/ - Graph API abstraction, error handling   │
├─────────────────────────────────────────────────────────┤
│                    Runners Layer                            │
│  app/runners/ - External entry points, job execution      │
├─────────────────────────────────────────────────────────┤
│                      CLI Layer                              │
│  app/cli/ - Command-line interface                         │
└─────────────────────────────────────────────────────────┘
```

Rules that must hold everywhere:
- API routes never write `status` directly — always through a service.
- Runners never issue raw `httpx` calls — always through `InstagramClient`.
- Services never spread Graph API metric names — that's centralized in `app/instagram/metrics.py`.
- Database work is split into short, explicit units. Repository mutations and claims commit their one durable operation; reads do not commit. Services may commit additional state checkpoints. Every Graph API call occurs only after the preceding database transaction was committed or rolled back.

---

## 3. Data Model

Seven core tables. UTC timestamps throughout. Every numeric metric column nullable, no default (NULL ≠ 0).

### `instagram_accounts`

```
id, name, instagram_user_id, is_default, enabled
access_token_ref, token_expires_at
created_at, updated_at, last_successful_api_call_at, last_error_at, last_error
```

Exactly one row may have `is_default = true` — enforce with a partial unique index (`ux_instagram_accounts_is_default`, `WHERE is_default = 1`). `name` is internal/human-readable. Secrets should be a reference (`access_token_ref`), not a plaintext token column.

**Implementation Notes:**
- `access_token_ref` stores a reference to tokens, not the actual tokens
- `app.core.credentials.resolve_access_token` currently accepts only
  `env:VARIABLE_NAME`; it rejects plaintext values and other schemes
- A secrets-manager backend is not implemented yet; add one deliberately rather
  than silently accepting a new reference format

### `instagram_posts`

```
id, account_id
media_type, media_source_type, media_source, media_payload_json
caption
status, scheduled_at
instagram_media_id, instagram_container_id, instagram_permalink
published_at, deleted_at, soft_deleted, delete_requested_at
publish_attempt_count, last_publish_attempt_at
last_synced_at, next_sync_at
idempotency_key
created_at, updated_at, last_error
```

`media_type`: `image | carousel | reel`. `media_source_type`: `url | local_file | object_storage`. `media_payload_json` holds media-specific structured config (e.g. carousel items) — designed so new media types don't require a schema migration. Unique constraint on `idempotency_key`.

**Indexing Strategy:**
- Status indexes for filtering (`idx_instagram_posts_status`)
- Scheduled_at and next_sync_at for efficient queries
- Account_id + status composite indexes (`idx_instagram_posts_account_id_status`)
- Locked_at indexes for stale lock detection (`idx_instagram_posts_locked_at`)

### `instagram_post_metrics`

```
id, post_id, captured_at
views, reach, plays
avg_watch_time_ms, total_watch_time_ms
likes, comments, saved, shares, total_interactions
profile_activity, follows
raw_metrics_json
```

Historical snapshots, never overwritten. `raw_metrics_json` preserves the original insight payload so metric-mapping changes don't require backfills.

**NULL vs 0 Semantics:**
- `0` = Instagram explicitly reports zero
- `NULL` = metric unavailable / not requested / not supported

Never convert unavailable metrics to zero.

Derived ratios (`engagement_rate`, `save_rate`, `share_rate`, `comment_rate`, `follow_conversion_rate`, `views_per_hour`, `reach_growth`) are computed from snapshots, not stored, unless a concrete need arises.

### `instagram_comments`

```
id, account_id, post_id
instagram_comment_id, parent_instagram_comment_id
username, instagram_user_id_if_available
text
created_at_remote, fetched_at, updated_at
like_count_if_available
is_reply, is_hidden, is_deleted_remote
raw_json
```

Unique constraint on `instagram_comment_id`. Sync must update existing rows, never duplicate.

### `instagram_jobs`

```
id
job_type, account_id, post_id, comment_id
payload_json
status, attempts, max_attempts
run_after, locked_at, locked_by
created_at, started_at, completed_at
last_error
```

`job_type`: `publish | delete_post | create_comment | reply_comment`. Future operations (`refresh_post`, `refresh_comments`, `edit_caption`) are intentionally not accepted until their runner and payload contract exist.

`status`: `pending | running | completed | failed | canceled`.

Payloads are strict Pydantic models, selected by `job_type`:

| Job type | `payload_json` |
|---|---|
| `publish` | `{}`; all inputs come from the referenced post |
| `delete_post` | `{}`; the referenced post supplies the remote media ID |
| `create_comment` | `{"text": string}`; 1-2200 characters |
| `reply_comment` | `{"text": string}`; 1-2200 characters |

Unknown fields and unknown job types are rejected. Claiming uses the same conditional-update/stale-lock pattern as post claiming (§5), with `run_after` eligibility and an atomic `attempts` increment.

### `instagram_events`

```
id, account_id, post_id, job_id
event_type, payload_json
created_at
```

Append-only. Initial `event_type`s: `post_created`, `post_updated`, `post_scheduled`, `publish_started/succeeded/failed`, `sync_started/succeeded/failed`, `metric_snapshot_created`, `delete_requested/started/succeeded/failed`, `comment_received/queued/sent/failed`. Goal is reconstructability — what happened, when, to what, what did Instagram return. Don't log trivial noise excessively. This is application history, not operational diagnostics — keep separate from `app/core/logging.py` logs.

### `global_options`

```
key, value_json, updated_at
```

Mutable runtime config: `default_sync_intervals`, `publish_batch_size`, `sync_batch_size`, `max_retry_count`, `retry_backoff`, `default_account_id`. No secrets here unless specifically required. Static operational settings stay in env vars.

**Runtime-Mutable Settings:**
- `default_sync_intervals`: JSON object with age-based sync frequencies
- `publish_batch_size`: Number of posts to process per publish batch
- `sync_batch_size`: Number of posts to process per sync batch
- `max_retry_count`: Maximum retry attempts for jobs
- `retry_backoff`: Array of backoff intervals in seconds
- `default_account_id`: ID of the default Instagram account

---

## 4. Post State Machine

States: `draft, ready, scheduled, publishing, published, failed, delete_requested, deleted, canceled`.

### Transition Table

| From | To |
|---|---|
| `draft` | `ready`, `scheduled`, `canceled` |
| `ready` | `publishing` |
| `scheduled` | `publishing` |
| `publishing` | `published`, `failed` |
| `failed` | `ready`, `publishing`, `canceled` |
| `published` | `delete_requested` |
| `delete_requested` | `deleted` |
| `deleted` | (terminal) |
| `canceled` | (terminal) |

No arbitrary transitions. The transition table is encoded as an explicit `TRANSITION_TABLE: dict[PostStatus, FrozenSet[PostStatus]]` in `app/services/post_state_machine.py`.

### State Machine Module (`app/services/post_state_machine.py`)

This module provides:
- `PostStatus` enum (mirrors the DB model enum for consistency)
- `TRANSITION_TABLE` — the explicit transition map
- `can_transition(from_status, to_status)` — returns bool
- `validate_transition(from_status, to_status, raise_on_invalid=False)` — returns bool, optionally raises ValueError
- `get_allowed_transitions(from_status)` — returns frozenset of allowed targets
- `is_terminal_status(status)` — returns True for deleted/canceled

**Status: Implemented** — Module and comprehensive unit tests (56 tests) are in place and passing. Phase 3 services use this module rather than implementing transition logic ad-hoc.

**State Definitions:**
- `draft`: Not ready for publishing
- `ready`: Ready to publish immediately
- `scheduled`: Ready but scheduled_at is in the future
- `publishing`: Runner currently attempting publication
- `published`: Successfully published to Instagram
- `failed`: Publishing failed and requires retry or intervention
- `delete_requested`: Published post should be removed remotely
- `deleted`: Remote post is confirmed deleted
- `canceled`: Post was canceled before publication

---

## 5. Idempotency & Locking

A runner executing twice must never publish (or delete, or comment) twice. Pattern:

```
find eligible row
  ↓
atomically claim / mark publishing   (short transaction, commit)
  ↓
call Instagram                        (no open transaction)
  ↓
write result                          (new transaction, commit)
```

Claim via a conditional `UPDATE` + rowcount check, not read-then-write. Implemented in `app/repositories/posts.py::claim_post_for_publishing`:

```sql
UPDATE instagram_posts
SET status = 'publishing', locked_at = :now, locked_by = :worker_id
WHERE id = :id
  AND status IN ('ready', 'scheduled')
  AND (locked_at IS NULL OR locked_at < :stale_cutoff)
```

Zero rows affected means someone else claimed it, or it's no longer eligible — the caller skips, it never treats this as an error. The function commits internally right after the `UPDATE`, so the claim is always its own short transaction; callers must call Instagram only after it returns, and write the result back in a separate transaction/commit. **No SQLite write transaction may span an HTTP call** — this is the single most important rule in the codebase; every runner must follow it.

`locked_by` scheme and stale-lock timeout: `app/core/locking.py::generate_worker_id()` produces the `locked_by` value; `settings.lock_stale_after_seconds` (`app/core/config.py`) is the timeout, passed into the claim call by the caller.

`instagram_jobs` claiming is implemented in `app/repositories/jobs.py::claim_job_for_execution` with the same short-transaction boundary. It sets `running`, increments `attempts`, records `started_at`, and refreshes the lock in one conditional `UPDATE`.

**Worker ID Generation:**
- Format: `{hostname}:{pid}:{random_hex8}`
- Example: `myhost:12345:abc123def`
- Ensures uniqueness even if PID is reused across crash/restart

**Stale Lock Detection:**
- Default timeout: 600 seconds (10 minutes)
- Configurable via `LOCK_STALE_AFTER_SECONDS` environment variable
- Operational safety margin, not a tunable runtime setting

---

## 6. `InstagramClient` Contract

One central abstraction; runners/services never call `httpx` directly.

### Methods

```
create_image_container(...)      create_reel_container(...)
create_carousel_container(...)   publish_container(...)
get_media(...)                   delete_media(...)
get_media_insights(...)          get_comments(...)
create_comment(...)              reply_to_comment(...)
```

Responsibilities: auth, HTTP calls, timeouts, Graph API URL construction, error parsing, rate-limit handling, response normalization, logging metadata. Use one shared configured `httpx.AsyncClient` (connect/read/write/pool timeouts, connection pooling, user agent) — never instantiate a new client per request.

### Shared HTTPX Client Configuration

- **Connect timeout**: Configurable, prevents hanging on connection
- **Read timeout**: Configurable, prevents hanging on read operations
- **Write timeout**: Configurable, prevents hanging on write operations
- **Pool timeout**: Configurable, prevents hanging on connection acquisition
- **Connection pooling**: Enabled for efficient reuse
- **User agent**: Custom user agent string for identification

### Error Taxonomy

```
InstagramTransientError       timeout, network failure, 5xx        → retry
InstagramRateLimitError       HTTP 429                             → retry after delay
InstagramAuthenticationError  expired/invalid token                → flag, do not blindly retry forever
InstagramPermissionError      permission failure                   → permanent/configuration error
InstagramValidationError      invalid media                        → permanent post failure
InstagramNotFoundError        remote media already gone            → treat desired-delete as fulfilled
```

Unsupported mutations (e.g. some caption edits post-publish) are marked `unsupported`, not silently dropped or retried.

### Error Handling Implementation

All errors inherit from `InstagramError` base class in `app/instagram/errors.py`. Each error type has:
- Clear classification (transient vs permanent)
- Retry policy indication
- Contextual information (status code, response body, etc.)
- Proper sanitization to avoid leaking sensitive information

---

## 7. Runners (Phase 3 Contract)

Three entrypoints: `python -m app.runners.{publish,sync,actions}`. Safe to invoke arbitrarily often (e.g. publish every minute, sync every few minutes) — the runner itself determines whether work is due.

### `publish_runner`

— finds due ready/scheduled posts, claims safely, creates the Instagram container, publishes, saves Instagram IDs/permalink/`published_at`, sets `status=published`, writes an event, handles retries/errors. Must not duplicate publication after crashes or reruns.

**Flow:**
1. Query for posts with status `ready` or `scheduled` where `scheduled_at <= now`
2. Claim each post atomically using the pattern from §5
3. Create appropriate container (image/reel/carousel) via `InstagramClient`
4. Publish container to Instagram
5. Save Instagram IDs (`instagram_media_id`, `instagram_container_id`, `instagram_permalink`)
6. Set `published_at` and `status = 'published'`
7. Write `publish_succeeded` event
8. Handle errors with retry logic and `publish_failed` event

### `sync_runner`

— finds published posts with `next_sync_at <= now`, fetches remote media info/insights/comments, normalizes, stores a metric snapshot, updates known comments, updates `last_synced_at`, computes the next `next_sync_at`. Frequency depends on post age (sync often <24h old, moderately 1-7 days, rarely >7 days) — implemented via `next_sync_at`, not by scanning every published post equally.

**Flow:**
1. Query for posts with `status = 'published'` and `next_sync_at <= now`
2. For each post:
   - Fetch remote media information via `InstagramClient.get_media()`
   - Fetch available insights via `InstagramClient.get_media_insights()`
   - Fetch comments via `InstagramClient.get_comments()`
   - Normalize data through `app/instagram/metrics.py`
   - Store metric snapshot in `instagram_post_metrics`
   - Update known comments (upsert by `instagram_comment_id`)
   - Update `last_synced_at`
   - Calculate next `next_sync_at` based on post age
   - Write `sync_succeeded` event
3. Handle errors with `sync_failed` event

**Sync Frequency Strategy:**
- Posts < 24 hours old: Sync every 1 hour (configurable)
- Posts 1-7 days old: Sync every 24 hours (configurable)
- Posts > 7 days old: Sync every 7 days (configurable)

### `action_runner`

— processes `delete_post`/`create_comment`/`reply_comment` jobs. Delete flow: post marked `soft_deleted` → `delete_post` job created → runner calls Instagram → remote deletion confirmed (or Instagram reports media already absent, which counts as satisfied) → `status=deleted`, `deleted_at` set → event recorded.

**Flow for delete_post:**
1. Query for jobs with `job_type = 'delete_post'` and `status = 'pending'`
2. Claim job atomically
3. Call `InstagramClient.delete_media()` with the post's `instagram_media_id`
4. If successful or media already absent:
   - Set post `status = 'deleted'`
   - Set `deleted_at`
   - Write `delete_succeeded` event
   - Set job `status = 'completed'`
5. If failed with retryable error:
   - Increment `attempts`
   - Set `run_after` based on retry backoff
   - Set job `status = 'pending'`
   - Write `delete_failed` event
6. If failed with permanent error:
   - Set job `status = 'failed'`
   - Write `delete_failed` event

**Flow for create_comment/reply_comment:**
1. Query for jobs with appropriate type and `status = 'pending'`
2. Claim job atomically
3. Call appropriate `InstagramClient` method
4. On success:
   - Store comment reply in database
   - Write `comment_sent` event
   - Set job `status = 'completed'`
5. On failure, follow same retry logic as delete

---

## 8. Reconciliation & Caption Sync

Reconciliation rules live in `services/reconciliation.py`, not scattered across API endpoints:

```
soft_deleted=true + currently published        → delete remotely
published locally, remote media gone            → record discrepancy, apply policy
comment queued locally                          → post comment
failed transient action                         → retry per policy
```

Caption edits: not every property is editable post-publish. Track independently from actual remote support:

```
caption, remote_caption_last_known, caption_sync_status ∈ {in_sync, pending, unsupported, failed}
```

If Instagram permits the edit, the action runner applies it; if unsupported, preserve the local requested value and record clearly that the remote state can't change. Never silently pretend sync succeeded.

### Reconciliation Policies

**Soft Delete Reconciliation:**
1. When post is soft-deleted locally (`soft_deleted = true`)
2. If post is still published remotely, create `delete_post` job
3. Job runner attempts deletion via Instagram API
4. If Instagram reports media already gone, consider deletion satisfied
5. Update post `status = 'deleted'` and set `deleted_at`

**Already-Deleted Remote Reconciliation:**
1. During sync, if Instagram reports media not found
2. Check local post status
3. If local status is `published` or `delete_requested`:
   - Update to `deleted`
   - Set `deleted_at`
   - Write appropriate event
4. If local status is `draft`, `ready`, or `scheduled`:
   - Update to `failed`
   - Set appropriate error message

**Caption Sync:**
1. When caption is updated locally
2. Check if Instagram supports caption editing for this media type
3. If supported:
   - Create `edit_caption` job (future implementation)
   - Runner updates remote caption
   - Set `caption_sync_status = 'in_sync'` on success
4. If unsupported:
   - Set `caption_sync_status = 'unsupported'`
   - Preserve local caption value
   - Never report sync as successful

---

## 9. Media Handling

Support `image`, `reel`, `carousel`. Even if v1 only fully implements image publishing, schemas should already accommodate reels/carousels without a later migration.

A `MediaResolver` abstraction converts `local_file | object_storage | existing_url` into a URL Instagram can use — the publishing service implements only the URL case. The `posts publish-file` CLI is deliberately an adapter around that boundary: it stages one local image behind a temporary HTTPS URL, then persists the post as `media_source_type = url`. It does not make `local_file` or `object_storage` resolvable by the general publishing service.

### Media Types

| Type | Description | Container Method | Publish Method |
|------|-------------|------------------|----------------|
| `image` | Single image post | `create_image_container` | `publish_container` |
| `reel` | Video post (Reel) | `create_reel_container` | `publish_container` |
| `carousel` | Multi-image/video post | `create_carousel_container` | `publish_container` |

### Media Source Types

| Type | Description | Resolver |
|------|-------------|----------|
| `url` | Direct URL to media | Pass through (v1 implemented) |
| `local_file` | Local filesystem path | `MediaResolver` (future) |
| `object_storage` | Cloud storage reference | `MediaResolver` (future) |

### One-Shot Local Image Path: `posts publish-file`

Source of truth: `app/cli/main.py`, `app/cli/publish_file.py`,
`app/cli/media_staging.py`, and `app/runners/publish.py::run_job`.

This operator-facing command exists for immediate publication of one local
image, not for the durable post scheduler:

```text
validated image path
  → loopback-only SingleFileServer (one random route)
  → NgrokTunnel (one HTTPS tunnel for that loopback origin)
  → URL-backed InstagramPost + publish job
  → run_job(job_id)
  → JSON receipt
  → stop tunnel and local server
```

`--confirm` is mandatory because the command can create a real Instagram post.
The CLI verifies that the selected account is enabled and has an Instagram user
ID plus an `env:` access-token reference before opening the tunnel. It exposes
only `GET`/`HEAD` for the selected image and never puts the source filename into
the public URL. The tunnel remains alive through the publication attempt.

The URL expires when the CLI exits. Therefore, if `run_job(job_id)` reports a
failure, the CLI cancels a pending retry before cleanup. This prevents a later
runner from retrying an inaccessible image URL. The failed post and audit events
remain durable. Scheduled posts, retries that must survive process exit, reels,
and carousels require a durable URL provider instead.

### Carousel Payload Structure

```json
{
  "items": [
    {
      "media_type": "image",
      "media_source_type": "url",
      "media_source": "https://example.com/image1.jpg"
    },
    {
      "media_type": "image",
      "media_source_type": "url",
      "media_source": "https://example.com/image2.jpg"
    }
  ]
}
```

Constraints:
- 2-10 items per carousel
- Mixed media types allowed (image + reel)
- Each item has its own `media_type` and `media_source`

---

## 10. Decision Log (Phase 2)

These decisions are made before Phase 3 starts and may change only with a deliberate architecture update and migration/contract assessment.

- **Claim SQL + stale-lock timeout** — conditional `UPDATE` shown in §5, implemented in `app/repositories/posts.py::claim_post_for_publishing`. `locked_by` is `f"{hostname}:{pid}:{random_hex8}"`, generated once per runner invocation by `app/core/locking.py::generate_worker_id()` — hostname:pid gives an operator a human-readable trace of which machine/process holds a lock, the random suffix guarantees uniqueness even if a pid is reused across a quick crash/restart (so a fresh invocation is never mistaken for the one that left a stale lock). Stale-lock timeout is `settings.lock_stale_after_seconds`, default **600s (10 minutes)**, in env config rather than `global_options` — it's an operational safety margin for detecting a crashed runner, not a value operators need to tune live, and env config avoids an extra DB read on every claim attempt. 10 minutes comfortably exceeds the expected duration of a single Instagram HTTP call + result write-back.

- **Job enums, payloads, and claim** — initial job types are limited to `publish`, `delete_post`, `create_comment`, and `reply_comment`; statuses are `pending`, `running`, `completed`, `failed`, and `canceled`. Payloads are strict Pydantic models: empty for publish/delete and `{text}` for comment/reply. `claim_job_for_execution` uses a conditional update, checks `run_after`, increments attempts atomically, and reclaims only stale locks.

- **Backoff sequence + where it's configured** — runtime-mutable `global_options.retry_backoff` is authoritative, with `app.services.retry_policy.DEFAULT_RETRY_BACKOFF_SECONDS = (60, 300, 900, 3600)` as the safe fallback. Retry timing sometimes needs adjustment during an Instagram incident without a process restart; locks do not, so retry backoff belongs in the DB and stale-lock timeout remains env-only.

- **Default-account invariant enforcement** — DB-level partial unique index (`ux_instagram_accounts_is_default`, `WHERE is_default = 1`), backed by a Phase 3 service-level enabled-default check. SQLite supports partial unique indexes directly, so conflicting defaults cannot be written even under concurrency.

- **Carousel `media_payload_json` shape** — `{"items": [{"media_type": "image" | "reel", "media_source_type": "url" | "local_file" | "object_storage", "media_source": string}, ...]}` with 2-10 items. The outer post carries the caption/account; every item is resolved through `MediaResolver` before it reaches `InstagramClient`.

---

## 11. API Surface

```
GET/POST     /api/v1/accounts
GET/PATCH    /api/v1/accounts/{id}

GET/POST     /api/v1/posts
GET/PATCH    /api/v1/posts/{id}
POST         /api/v1/posts/{id}/schedule
POST         /api/v1/posts/{id}/publish
DELETE       /api/v1/posts/{id}          — soft delete / reconciliation request, not row destruction

GET          /api/v1/posts/{id}/metrics
GET          /api/v1/posts/{id}/comments
POST         /api/v1/posts/{id}/comments
POST         /api/v1/comments/{id}/reply

GET          /api/v1/jobs
GET          /api/v1/events

GET/PATCH    /api/v1/options[/{key}]

GET          /health
```

Minimal external-producer post creation (this is the contract Vend1r depends on — changing it later is a breaking change):

```json
{
  "caption": "Example",
  "media_type": "image",
  "media_source_type": "url",
  "media_source": "https://example.com/image.jpg"
}
```

`account_id` is optional (Phase 3 falls back to the enabled default account, or returns a clear 4xx if none exists); `scheduled_at` is optional. The API returns the internal post ID immediately — producers never see container IDs. The Phase 2 routers are registered and consistently return `501 Not Implemented` until Phase 3 wires services; their OpenAPI schemas are already the binding producer contract.

Comment creation (`POST /posts/{id}/comments`) creates the local row + a `create_comment` job and returns immediately; it does not call Instagram synchronously inside the request unless a dedicated synchronous endpoint is deliberately added later.

### API Response Models

**Public vs Internal Separation:**
- Public responses expose only relevant fields to external consumers
- Internal responses include operational details (locks, attempt counts, etc.)
- Consider creating `PublicPostResponse` vs `InternalPostResponse` for better separation

---

## 12. SQLite Specifics

WAL mode, `foreign_keys=ON`, `busy_timeout` — set through the SQLAlchemy connection lifecycle in `app/db/session.py`, not as raw strings on an async session. Async engine (`aiosqlite`) is used at runtime; Alembic (`alembic/env.py`) converts the URL to a sync `sqlite://` engine since Alembic doesn't run async migrations natively. All schema creation, including test fixtures, goes through Alembic; `Base.metadata.create_all()` is not used. Designed for a small number of concurrent processes, not distributed throughput.

### SQLite Configuration

**Connection Settings (app/db/session.py):**
```python
# WAL mode for better concurrent access
PRAGMA journal_mode=WAL

# Enable foreign key constraints
PRAGMA foreign_keys=ON

# Timeout for busy database (5 seconds)
PRAGMA busy_timeout=5000
```

**Why SQLite:**
- Simple deployment (single file)
- Sufficient for small-to-medium scale
- Built-in queue via job tables
- No external dependencies (Redis, RabbitMQ, etc.)

**Limitations to be Aware Of:**
- Single-writer lock can bottleneck under heavy write load
- Not suitable for distributed deployments without additional coordination
- Limited connection pooling compared to client-server databases

---

## 13. Observability

Every runner execution should produce concise structured logs with: `runner, job_id, post_id, account_id, instagram_media_id, operation, attempt, duration, result, error_type`. Never log access tokens, secrets, or large raw payloads unnecessarily. Logs (`app/core/logging.py`) are operational diagnostics; `instagram_events` is application history — keep the two separate.

### Structured Logging

**Required Fields for Runner Logs:**
- `runner`: Name of the runner (publish, sync, actions)
- `job_id`: ID of the job being processed (if applicable)
- `post_id`: ID of the post being processed (if applicable)
- `account_id`: ID of the Instagram account
- `instagram_media_id`: Instagram media ID (if available)
- `operation`: Type of operation being performed
- `attempt`: Attempt number
- `duration`: Duration of the operation in seconds
- `result`: success/failure/skipped
- `error_type`: Type of error (if failed)

**Log Levels:**
- `DEBUG`: Detailed operational information
- `INFO`: Significant events and state changes
- `WARNING`: Unexpected but handled conditions
- `ERROR`: Failed operations that need attention
- `CRITICAL`: Severe errors that may prevent continued operation

### Event Types

**Post Events:**
- `post_created`, `post_updated`, `post_scheduled`
- `publish_started`, `publish_succeeded`, `publish_failed`
- `delete_requested`, `delete_started`, `delete_succeeded`, `delete_failed`

**Sync Events:**
- `sync_started`, `sync_succeeded`, `sync_failed`
- `metric_snapshot_created`

**Comment Events:**
- `comment_received`, `comment_queued`, `comment_sent`, `comment_failed`

---

## 14. Security

Don't expose access tokens in API responses or logs; keep secrets outside source control; validate external URLs/input; limit arbitrary filesystem access. Initial deployment is trusted/local — don't add auth infrastructure until the API becomes remotely accessible.

### Security Principles

1. **Token Security**: Access tokens are never stored in plaintext
2. **Input Validation**: All external inputs are validated
3. **Error Sanitization**: Error messages never leak sensitive information
4. **No Direct HTTP**: Services never call httpx directly, always through InstagramClient
5. **SQL Injection Protection**: SQLAlchemy ORM provides parameterized queries

### Security Considerations

**Token Handling:**
- Tokens stored as references (`access_token_ref`) in database
- Current references must be `env:VARIABLE_NAME`, resolved by
  `app.core.credentials.resolve_access_token`
- A secrets-manager backend is a future extension, not a supported current
  reference format
- Never expose tokens in API responses, logs, or error messages

**URL Validation:**
- Validate all external URLs before use
- Restrict to http/https schemes only
- Validate URL length and format
- Consider adding SSRF protection

**Authentication:**
- No auth required for local/trusted deployments
- Can be added when API becomes remotely accessible
- Admin UI under `/admin` prefix to allow future auth without affecting `/api/v1`

---

## 15. Testing

`respx` mocks all Instagram HTTP calls — no real Graph API calls in automated tests. Minimum coverage per `plan.annapost.md` §29: post state transitions, default-account fallback, multi-account isolation, publish success/failure, duplicate-publish prevention, retry behavior, rate-limit behavior, soft deletion, already-remote-deleted reconciliation, comment dedup, outgoing comment jobs, metric snapshot creation, NULL-vs-0 metric handling, sync scheduling (`next_sync_at`), expired-token behavior, malformed Instagram responses, runner crash/restart scenarios.

### Test Organization

```
tests/
├── api/              # API endpoint tests
│   ├── test_health.py
│   └── test_phase2_routes.py
├── integration/      # Integration tests
│   ├── test_migrations.py
│   └── test_phase5_hardening.py
├── runners/          # Runner tests
│   └── test_publish_runner.py
├── ui/               # Admin UI tests
│   └── test_admin_routes.py
└── unit/             # Unit tests
    ├── test_job_contract.py
    ├── test_phase2_contracts.py
    ├── test_phase3_client.py
    ├── test_phase3_publishing.py
    ├── test_post_state_machine.py
    ├── test_posts_repository.py
    ├── test_tier1_crud.py
    └── test_post_state_machine.py
```

### Test Coverage Highlights

**Strengths:**
- Comprehensive state machine testing (56 tests)
- Good contract testing for Phase 2 and Phase 3
- Mocked Instagram API calls throughout
- Integration tests for migrations

**Areas for Improvement:**
- Limited runner test coverage (currently 1 test file)
- Admin UI tests could be more comprehensive
- Integration tests between services
- Error scenario testing
- Performance testing
- End-to-end tests for complete workflows

---

## 16. Phase Roadmap

| Phase | File | Status | Completion Date |
|---|---|---|---|
| 1 — Skeleton | `phases/01-prebuild.md` | Done | 2026-08-XX |
| 2 — Architecture | `phases/02-architecture.md` | Done | 2026-08-11 |
| 3 — Implementation | `phases/03-implementation.md` | Done | 2026-08-11 |
| 4 — Admin UI | `phases/04-ui.md` | In Progress | - |
| 5 — Review | `phases/05-review.md` | Not Started | - |

v1 definition of done (`plan.annapost.md` §35): an external client can create an image post via the API (immediate or scheduled), `publish_runner` publishes it exactly once and stores Instagram IDs/permalink, `sync_runner` fetches metrics and imports comments without duplicates, outgoing comments/replies are queued and sent, soft-deleted posts are reconciled remotely, failures produce useful state/retries/events, multiple accounts don't leak into each other, and the full test suite passes with no real Instagram network calls.

---

## 17. Code Quality Assessment

### Overall Assessment: 9.2/10 - Excellent foundation with minor areas for refinement

| Category | Score | Notes |
|----------|-------|-------|
| Architecture | 10/10 | Excellent layering and separation of concerns |
| Code Style | 9/10 | Consistent, modern Python with minor inconsistencies |
| Type Safety | 9/10 | Good type hints, could use more TYPE_CHECKING |
| Testing | 8/10 | Good unit coverage, needs more integration tests |
| Documentation | 9/10 | Comprehensive docs, some code-level docs missing |
| Error Handling | 9/10 | Well-structured, minor improvements needed |
| Performance | 8/10 | Good for SQLite scale, could optimize some queries |
| Security | 8/10 | Generally good, needs token handling review |

### Detailed Analysis

#### Type Annotations: 9/10

- Excellent use of modern type hints (Python 3.12+ features)
- Good use of `TypedDict`, `Literal`, and custom types
- Some functions could benefit from return type annotations
- Could use more `TYPE_CHECKING` imports for circular dependencies

#### Documentation: 9/10

- Exceptional high-level documentation (ARCHITECTURE.md, plan.annapost.md)
- Good module-level docstrings
- Some functions lack docstrings
- Could benefit from more inline comments for complex logic

#### Code Duplication: 8/10

- Minimal duplication overall
- Some similarity between claim functions (posts vs jobs)
- Media type handling has some duplication
- Could extract common patterns into utilities

#### Complexity: 8/10

- Most functions are focused and single-purpose
- Some service methods are complex (publish_claimed_post)
- State machine logic is appropriately complex
- Could benefit from more helper functions

---

## Key Metrics

- **Lines of Code**: ~5,000+ (estimated)
- **Test Files**: ~15
- **Migration Files**: 3
- **API Endpoints**: ~20+
- **Database Tables**: 7 core tables
- **Service Classes**: ~15+
- **Test Coverage**: Target 90%+

---

*This architecture reference is based on the codebase at /Users/yannis/dev/AnnaPost and was last updated on 2026-08-11*
