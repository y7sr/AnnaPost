# Standalone Instagram Publishing System — Implementation Plan

## Goal

Build a small, standalone Instagram publishing and management application, independent from Vend1r.

Vend1r or any other external system may create or modify Instagram publishing data through the API, but this project owns:

* its own database
* its own API
* Instagram account configuration
* publishing
* synchronization
* comments/replies
* deletion/reconciliation
* metrics/history
* retries and operational state

The system must be optimized specifically for Instagram publishing and management.

Do not couple it to Vend1r internals.

---

## 1. Technology Stack

Use:

```text
Python 3.12+
FastAPI
Pydantic v2
SQLAlchemy 2.x
SQLite
Alembic
HTTPX

pytest
pytest-asyncio
pytest-cov
respx

ruff
python-dotenv
```

Optional:

```text
structlog
```

Do not introduce unless clearly necessary:

```text
Redis
Celery
RabbitMQ
Docker-only architecture
external scheduler infrastructure
```

The application should remain simple enough to run locally or on a small server.

---

## 2. Core Architecture

Use clear separation between:

```text
API layer
database/models
schemas
services
Instagram API client
runners
repositories/query helpers
configuration
tests
```

Conceptually:

```text
External Producer
    ↓
FastAPI
    ↓
Database
    ↓
Runners
    ↓
InstagramClient
    ↓
Instagram Graph API
```

Primary architectural principle:

```text
DATABASE = desired state + internal history
INSTAGRAM = external state
RUNNERS = reconciliation between both
```

External systems should mostly interact with the database through the API.

They should not need to know how publishing, retries or Instagram synchronization work.

---

## 3. Multi-Account Support

Multi-account support is mandatory from the beginning.

Initially there may be only one account, designated as the default account.

Never hardcode the system around one Instagram account.

Create:

```text
instagram_accounts
```

Suggested fields:

```text
id
name
instagram_user_id
is_default
enabled

access_token_ref
token_expires_at

created_at
updated_at
last_successful_api_call_at
last_error_at
last_error
```

`name` is the internal human-readable account name.

Every Instagram post must reference:

```text
account_id
```

Do not duplicate account credentials across post rows.

Exactly one account may be marked as default.

If a POST creation API request omits `account_id`, use the enabled default account.

If no default account exists, reject the request clearly.

Secrets should preferably come from environment/configuration or a secret reference rather than being casually stored in plaintext fields.

---

## 4. Database Tables

Minimum required tables:

```text
instagram_accounts
instagram_posts
instagram_post_metrics
instagram_comments
instagram_jobs
instagram_events
global_options
```

Use normal foreign keys and indexes.

Use timestamps consistently in UTC.

---

# 5. instagram_posts

This is the central desired-state table.

Suggested fields:

```text
id
account_id

media_type
media_source_type
media_source
media_payload_json

caption

status
scheduled_at

instagram_media_id
instagram_container_id
instagram_permalink

published_at
deleted_at

soft_deleted
delete_requested_at

publish_attempt_count
last_publish_attempt_at

last_synced_at
next_sync_at

idempotency_key

created_at
updated_at

last_error
```

Potential `media_type` values:

```text
image
carousel
reel
```

Potential `media_source_type` values:

```text
url
local_file
object_storage
```

Design this so new media types can be added without redesigning the entire table.

`media_payload_json` may hold media-specific structured configuration such as carousel items.

---

## 6. Post State Machine

Use a defined state machine.

Initial states:

```text
draft
ready
scheduled
publishing
published
failed
delete_requested
deleted
canceled
```

Recommended meaning:

```text
draft
not ready for publishing

ready
ready to publish immediately

scheduled
ready but scheduled_at is in the future

publishing
runner currently attempting publication

published
successfully published to Instagram

failed
publishing failed and requires retry or intervention

delete_requested
published post should be removed remotely

deleted
remote post is confirmed deleted

canceled
post was canceled before publication
```

Do not allow arbitrary state transitions.

Implement transition logic in a service rather than letting API endpoints modify status freely.

Example valid transitions:

```text
draft -> ready
draft -> scheduled
draft -> canceled

ready -> publishing
scheduled -> publishing

publishing -> published
publishing -> failed

failed -> ready
failed -> publishing
failed -> canceled

published -> delete_requested
delete_requested -> deleted
```

Exact behavior may be adjusted during implementation, but keep transitions explicit.

---

## 7. Idempotency and Locking

This is critical.

A runner executing twice must never accidentally publish a post twice.

Each publishable post should have:

```text
idempotency_key
status
publish_attempt_count
last_publish_attempt_at
```

Implement DB-level claiming before performing external work.

Conceptual flow:

```text
find eligible row
↓
atomically claim / mark publishing
↓
commit
↓
call Instagram
↓
update result
```

Avoid holding a SQLite transaction open while waiting for HTTP responses.

Use short transactions.

Multiple runner processes should be able to run without causing duplicate actions.

If needed, introduce fields such as:

```text
locked_at
locked_by
```

but keep the implementation simple.

---

# 8. instagram_jobs

Use a lightweight internal job table for asynchronous desired actions.

Suggested fields:

```text
id

job_type
account_id
post_id
comment_id

payload_json

status
attempts
max_attempts

run_after
locked_at
locked_by

created_at
started_at
completed_at

last_error
```

Initial `job_type` values:

```text
publish
delete_post
create_comment
reply_comment
```

Potential future jobs:

```text
refresh_post
refresh_comments
edit_caption
```

Possible statuses:

```text
pending
running
completed
failed
canceled
```

Jobs must be idempotent where practical.

Do not use a heavy queue system initially.

SQLite is the queue.

---

# 9. Runners

Implement runners as simple Python entrypoints.

Desired commands:

```text
python -m app.runners.publish
python -m app.runners.sync
python -m app.runners.actions
```

Optional dedicated command if cleaner:

```text
python -m app.runners.comments
```

Prefer three runners:

```text
publish_runner
sync_runner
action_runner
```

## publish_runner

Responsibilities:

```text
find due ready/scheduled posts
claim safely
create required Instagram media/container
publish
save Instagram IDs
save permalink
set published_at
set status published
write event
handle retries/errors
```

Must not duplicate publication after crashes or reruns.

---

## sync_runner

Responsibilities:

```text
find published posts whose next_sync_at <= now
fetch current remote media information
fetch available insights
fetch comments
normalize data
store metric snapshot
update known comments
update post last_synced_at
calculate next_sync_at
write errors/events where useful
```

Sync frequency should depend on post age.

Example strategy:

```text
age < 24h
sync frequently

1–7 days
sync moderately

> 7 days
sync rarely
```

Implement this through `next_sync_at`, not by scanning every published post equally every run.

Make intervals configurable.

---

## action_runner

Responsibilities:

```text
process delete jobs
process comment jobs
process reply jobs
later process other supported mutation jobs
```

Example delete flow:

```text
DB post marked soft_deleted
↓
create delete_post job if needed
↓
action_runner calls Instagram
↓
remote deletion confirmed
↓
post.status = deleted
post.deleted_at set
↓
event recorded
```

If Instagram reports the media is already absent, treat the desired state as satisfied and mark it deleted locally.

---

# 10. Reconciliation

The system should continuously reconcile local desired state with Instagram state.

Examples:

```text
soft_deleted = true + currently published
→ delete remotely

published locally but remote media no longer exists
→ record discrepancy and update according to defined policy

comment queued locally
→ post comment

failed transient action
→ retry according to policy
```

Do not scatter reconciliation rules through API endpoints.

Put them in dedicated services.

---

# 11. Caption Changes

Do not assume every Instagram media property can be edited after publication.

Model local caption changes independently from actual remote support.

For published posts:

```text
caption
remote_caption_last_known
caption_sync_status
```

Potential states:

```text
in_sync
pending
unsupported
failed
```

If Instagram/API permits a requested edit, action runner may apply it.

If unsupported, preserve the local requested value and clearly record that the remote state cannot be changed.

Do not silently pretend synchronization succeeded.

---

# 12. instagram_post_metrics

Store historical snapshots, not just the latest values.

Fields:

```text
id
post_id
captured_at

views
reach
plays

avg_watch_time_ms
total_watch_time_ms

likes
comments
saved
shares
total_interactions

profile_activity
follows

raw_metrics_json
```

Important:

```text
0 = Instagram explicitly reports zero
NULL = metric unavailable / not requested / not supported
```

Never convert unavailable metrics to zero.

Metrics availability varies by:

```text
media type
account type
Instagram Graph API version
metric deprecations/changes
```

`raw_metrics_json` must preserve the original insight payload.

This allows future migrations if Instagram changes metric names or semantics.

Do not store every derived ratio unless needed.

Derived values should normally be calculated from snapshots:

```text
engagement_rate
save_rate
share_rate
comment_rate
follow_conversion_rate
views_per_hour
reach_growth
```

---

# 13. instagram_comments

Store remote comments locally.

Suggested fields:

```text
id
account_id
post_id

instagram_comment_id
parent_instagram_comment_id

username
instagram_user_id_if_available

text

created_at_remote
fetched_at
updated_at

like_count_if_available

is_reply
is_hidden
is_deleted_remote

raw_json
```

Use a unique constraint on:

```text
instagram_comment_id
```

Comment synchronization must update existing rows instead of creating duplicates.

---

# 14. Sending Comments and Replies

Comments created by our system should flow through jobs.

API example:

```text
POST /posts/{post_id}/comments
```

This should:

```text
create local outgoing comment/action
create create_comment job
return immediately
```

Do not perform the Instagram HTTP call directly inside the API request unless deliberately needed for a special synchronous endpoint.

Replies should work similarly.

Store:

```text
local state
remote instagram_comment_id
attempts
errors
timestamps
```

---

# 15. instagram_events

Implement an append-only operational/audit log.

Suggested fields:

```text
id
account_id
post_id
job_id

event_type
payload_json

created_at
```

Initial events:

```text
post_created
post_updated
post_scheduled

publish_started
publish_succeeded
publish_failed

sync_started
sync_succeeded
sync_failed

metric_snapshot_created

delete_requested
delete_started
delete_succeeded
delete_failed

comment_received
comment_queued
comment_sent
comment_failed
```

Do not log trivial noise excessively.

The goal is reconstructability:

```text
What happened?
When?
To which post/account?
What did Instagram return?
```

---

# 16. global_options

Create a simple configuration table for mutable application settings.

Suggested structure:

```text
key
value_json
updated_at
```

Possible values:

```text
default_sync_intervals
publish_batch_size
sync_batch_size
max_retry_count
retry_backoff
default_account_id
```

Do not put secrets here unless specifically required.

Static operational settings may remain environment variables.

---

# 17. Instagram API Client

Create one central client abstraction.

Example:

```text
InstagramClient
```

Responsibilities:

```text
authentication
HTTP calls
timeouts
Graph API URL construction
error parsing
rate-limit handling
response normalization
logging metadata
```

Potential methods:

```text
create_image_container(...)
create_reel_container(...)
create_carousel_container(...)
publish_container(...)

get_media(...)
delete_media(...)

get_media_insights(...)
get_comments(...)

create_comment(...)
reply_to_comment(...)
```

Do not let runners perform raw HTTPX calls directly.

Runners call services.

Services call `InstagramClient`.

---

# 18. HTTPX Configuration

Use a shared configured `httpx.AsyncClient`.

Configure:

```text
connect timeout
read timeout
write timeout
pool timeout
connection pooling
user agent
```

Do not instantiate a new client for every request.

Handle:

```text
network failures
timeouts
HTTP 429
5xx
Graph API error payloads
invalid/expired access tokens
invalid media
permission errors
```

---

# 19. Error Classification

Differentiate transient and permanent failures.

Examples:

```text
timeout
→ transient retry

network failure
→ transient retry

HTTP 429
→ retry after appropriate delay

Instagram 5xx
→ retry

expired token
→ account/auth error, do not blindly retry forever

permission failure
→ permanent/configuration error

invalid media
→ permanent post failure

unsupported mutation
→ mark unsupported

remote media already deleted
→ desired delete state considered fulfilled
```

Introduce typed internal exceptions if useful:

```text
InstagramTransientError
InstagramRateLimitError
InstagramAuthenticationError
InstagramPermissionError
InstagramValidationError
InstagramNotFoundError
```

---

# 20. Retry Strategy

Use bounded retries.

Suggested job fields:

```text
attempts
max_attempts
run_after
last_error
```

Use backoff.

Conceptually:

```text
1 min
5 min
15 min
1 h
...
```

Exact timing should be configurable.

Do not retry permanent errors.

---

# 21. API

Provide a clean `/api/v1` API.

Initial endpoints:

```text
GET    /api/v1/accounts
POST   /api/v1/accounts
GET    /api/v1/accounts/{id}
PATCH  /api/v1/accounts/{id}

GET    /api/v1/posts
POST   /api/v1/posts
GET    /api/v1/posts/{id}
PATCH  /api/v1/posts/{id}

POST   /api/v1/posts/{id}/schedule
POST   /api/v1/posts/{id}/publish
DELETE /api/v1/posts/{id}

GET    /api/v1/posts/{id}/metrics
GET    /api/v1/posts/{id}/comments

POST   /api/v1/posts/{id}/comments
POST   /api/v1/comments/{id}/reply

GET    /api/v1/jobs
GET    /api/v1/events

GET    /api/v1/options
PATCH  /api/v1/options/{key}

GET    /health
```

`DELETE /posts/{id}` should normally request soft deletion/reconciliation rather than immediately destroying the database row.

Do not physically delete post history by default.

---

# 22. External Producer API

The API must be easy for Vend1r or another producer to use.

Minimal post creation should allow:

```json
{
  "caption": "Example",
  "media_type": "image",
  "media_source_type": "url",
  "media_source": "https://example.com/image.jpg"
}
```

If no account is supplied:

```text
use default account
```

Optional scheduling:

```json
{
  "scheduled_at": "2026-08-12T09:00:00Z"
}
```

Optional explicit account:

```json
{
  "account_id": 2
}
```

Return the internal post ID immediately.

External producers must not need to understand Graph API container IDs.

---

# 23. Media Handling

Keep Instagram media handling separated from generic post metadata.

Support initially:

```text
single image
reel
carousel
```

If the first implementation only fully supports image publishing, still design the schemas so reels and carousels do not require a migration of the conceptual model.

Validate URLs and media requirements before creating publish jobs where practical.

Keep staging/object-storage logic behind a media service.

Potential abstraction:

```text
MediaResolver
```

which converts:

```text
local file
object storage reference
existing URL
```

into a URL suitable for Instagram when necessary.

---

# 24. Scheduling

Do not embed a heavy scheduler initially.

Runners are invoked externally.

Examples:

```text
cron
systemd timer
launchd
manual CLI
small future scheduler
```

Runner execution should be safe even if invoked frequently.

Example:

```text
publish every minute
sync every few minutes
actions every minute
```

The runner itself determines whether work is due.

---

# 25. CLI

Provide useful operational commands.

Example:

```text
python -m app.cli.main accounts list
python -m app.cli.main posts list
python -m app.cli.main posts show 123
python -m app.cli.main jobs list
python -m app.cli.main runner publish
python -m app.cli.main runner sync
python -m app.cli.main runner actions

# Real, one-shot local image publication. Requires explicit confirmation.
python -m app.cli.main posts publish-file ./image.jpg --caption "Caption" --confirm
```

`posts publish-file` is a distinct immediate-publication adapter: it stages one
local image through a temporary ngrok HTTPS URL, queues a normal URL-backed
post, and processes only that job. Its temporary URL must not be used for
scheduled work or retries that outlive the command.

The dedicated runner module commands may remain as well.

Keep CLI thin; reuse application services.

---

# 26. Repository Structure

Suggested structure:

```text
app/
    main.py

    api/
        routes/
            accounts.py
            posts.py
            comments.py
            metrics.py
            jobs.py
            events.py
            options.py

    core/
        config.py
        logging.py

    db/
        base.py
        session.py
        models/

    schemas/
        account.py
        post.py
        comment.py
        metrics.py
        job.py
        event.py

    repositories/
        accounts.py
        posts.py
        comments.py
        jobs.py
        metrics.py

    services/
        accounts.py
        posts.py
        publishing.py
        sync.py
        actions.py
        comments.py
        reconciliation.py
        media.py

    instagram/
        client.py
        errors.py
        schemas.py
        metrics.py

    runners/
        publish.py
        sync.py
        actions.py

    cli/
        main.py

tests/
    unit/
    integration/
    api/
    runners/

alembic/
```

Avoid unnecessary abstraction layers if they add no value.

Repositories may be kept thin.

---

# 27. SQLite Rules

SQLite is intentional.

Configure appropriately:

```text
WAL mode
foreign_keys = ON
busy_timeout
```

Keep write transactions short.

Do not hold a transaction while performing Instagram HTTP calls.

Runner flow should generally be:

```text
read/claim DB
commit
HTTP operation
write result
commit
```

Design for a small number of concurrent processes, not massive distributed throughput.

---

# 28. Alembic

All schema changes must use Alembic migrations.

Initial migration should create the full core schema.

Do not rely on:

```text
Base.metadata.create_all()
```

as the production migration strategy.

Tests may use temporary databases as appropriate.

---

# 29. Testing

Use:

```text
pytest
pytest-asyncio
pytest-cov
respx
```

Test at least:

```text
post state transitions
default account fallback
multi-account isolation
publishing success
publishing failure
duplicate publish prevention
retry behavior
rate-limit behavior
soft deletion
already-remote-deleted reconciliation
comment ingestion deduplication
outgoing comment jobs
metrics snapshot creation
NULL vs 0 metrics handling
sync scheduling / next_sync_at
expired token behavior
Instagram malformed responses
runner crash/restart scenarios
```

HTTP calls to Instagram must be mocked with `respx`.

Do not make real Instagram requests during automated tests.

---

# 30. Observability

Every runner execution should produce concise structured logs.

Important fields:

```text
runner
job_id
post_id
account_id
instagram_media_id
operation
attempt
duration
result
error_type
```

Avoid logging:

```text
access tokens
secrets
large raw payloads unnecessarily
```

`instagram_events` is application history.

Logs are operational diagnostics.

Keep both concepts separate.

---

# 31. Security

At minimum:

```text
do not expose access tokens in API responses
do not log tokens
keep secrets outside source control
validate external URLs/input
limit arbitrary filesystem access
```

If the API later becomes remotely accessible, authentication can be added.

For initial trusted/local deployment, do not overengineer auth unless needed.

---

# 32. API Version Adaptation

Instagram Graph API metrics and endpoints change over time.

Therefore:

```text
centralize Graph API version
centralize metric mapping
preserve raw API payloads
normalize into stable internal field names
```

Do not spread Graph API metric names through business logic.

Example:

```text
Instagram insight metric
        ↓
instagram/metrics.py
        ↓
NormalizedPostMetrics
        ↓
instagram_post_metrics
```

---

# 33. Implementation Order

Implement in phases.

## Phase 1 — Skeleton

```text
project structure
configuration
FastAPI
SQLAlchemy
SQLite
Alembic
health endpoint
test infrastructure
```

## Phase 2 — Core Database

```text
accounts
posts
jobs
events
global_options
metrics
comments
```

Create migrations and CRUD tests.

## Phase 3 — Accounts + Posts API

```text
account CRUD
default account behavior
post CRUD
state machine
soft delete
schedule handling
```

## Phase 4 — Instagram Client

```text
HTTPX client
authentication
typed errors
mocked client tests
basic media creation/publishing
```

## Phase 5 — Publishing

```text
publish service
publish runner
claiming/idempotency
retry behavior
events
```

## Phase 6 — Synchronization

```text
media fetch
insights
metric normalization
metric snapshots
comment synchronization
next_sync_at strategy
```

## Phase 7 — Actions

```text
delete reconciliation
outgoing comments
replies
job retries
```

## Phase 8 — Operational Hardening

```text
CLI
structured logging
runner crash tests
SQLite concurrency tests
configuration cleanup
API validation
```

---

# 34. Important Design Constraints

Do not:

```text
couple this application to Vend1r
hardcode one Instagram account
publish directly from Vend1r
overwrite historical metrics
treat missing metrics as zero
perform external HTTP while holding long SQLite write transactions
duplicate Instagram API logic across runners
silently retry permanent errors forever
physically delete operational history by default
add Redis/Celery without a demonstrated need
```

Do:

```text
make API the integration boundary
keep runners independently executable
make operations idempotent
preserve raw Instagram responses where useful
keep all posts account-specific
use append-only events for important actions
store historical metrics
support eventual reconciliation
design around Instagram API instability/version changes
```

---

# 35. Definition of Done for v1

v1 is complete when the following flow works reliably:

```text
1. Create/configure Instagram account.
2. Mark one account as default.
3. External client creates an image post through API.
4. Post can be immediate or scheduled.
5. publish_runner discovers and publishes it exactly once.
6. Instagram IDs/permalink/publication timestamp are stored.
7. sync_runner fetches current metrics.
8. Historical metric snapshots are stored.
9. sync_runner imports comments without duplicates.
10. API can queue an outgoing comment/reply.
11. action_runner posts it and records result.
12. API can soft-delete a published post.
13. action_runner/reconciliation removes it remotely.
14. Failures generate useful state, retries and events.
15. Multiple Instagram accounts work without cross-account leakage.
16. Full automated test suite passes without real Instagram network calls.
```

The priority is a compact, dependable system rather than a broad platform. Keep abstractions only where they reduce duplication or protect us from Instagram-specific complexity.
