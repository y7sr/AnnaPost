# Phase 2 — Architecture (Hard)

Reference: `plan.annapost.md` sections 3–23, 27, 32; supersedes/expands old section 33 "Phase 2 — Core Database".

## Goal

Make every decision that is expensive to reverse later, and encode it as schema, typed contracts, and stub endpoints — before any real business logic is written in Phase 3. Mistakes here (schema shape, idempotency semantics, transition rules, client contract) turn into migrations and rewrites later; mistakes in Phase 3 are just bugs.

Difficulty: **hard** — this is a design phase, not a typing phase. Get review/sign-off on the deliverables below before starting Phase 3.

## Completion Record

**Status: COMPLETED**  
**Completion Date:** 2026-08-11  
**Reviewed By:** Deep Code Review (see `annapost-deep-code-review.md`)  

Completed 2026-08-11. The reviewed Phase 2 boundary is the full `001 → 002` Alembic chain, typed schema/client/media/metric contracts, explicit claim and retry policies, registered `/api/v1` stub routers, reconciliation policy, and the focused acceptance tests under `tests/unit/test_phase2_contracts.py` and `tests/api/test_phase2_routes.py`. Business behavior, HTTPX request bodies, and runners remain deliberately deferred to Phase 3.

**Phase 2 Artifacts:**
- [x] Complete data model (all 7 core tables)
- [x] State machine module with transition table and unit tests (56 tests)
- [x] Idempotency & locking design with claim SQL
- [x] InstagramClient contract with typed exceptions
- [x] Job enums, payloads, and claim strategy
- [x] Retry & error classification policy
- [x] Media abstraction (MediaResolver interface)
- [x] API contract (all endpoints with stub responses)
- [x] Reconciliation policy (documents in services/reconciliation.py)
- [x] ARCHITECTURE.md decision log
- [x] Alembic migrations (001, 002)

---

## Tasks

### 1. Full data model (sections 4–16)

Design and migrate **all** core tables in one reviewed Alembic revision (or a tight, reviewed sequence):
`instagram_accounts`, `instagram_posts`, `instagram_post_metrics`, `instagram_comments`, `instagram_jobs`, `instagram_events`, `global_options`.

**✅ COMPLETED**

- [x] Turn every field list in sections 3, 5, 8, 12, 13, 15, 16 into concrete SQL: types, nullability, defaults, FKs, indexes
- [x] Enforce invariants at the DB level where possible:
  - exactly one `instagram_accounts` row with `is_default = true` (partial unique index if the dialect/SQLAlchemy setup supports it cleanly on SQLite; otherwise document that it's app-enforced and why)
  - unique constraint on `instagram_comments.instagram_comment_id` (section 13)
  - unique constraint on `instagram_posts.idempotency_key` (section 7)
- [x] Every metric numeric column in `instagram_post_metrics` must be nullable with no default — NULL means "unavailable", never coerce to 0 (section 12). This is a schema-level decision, not just an application convention.
- [x] UTC timestamps everywhere, consistently typed.

### 2. Post state machine (section 6)

**✅ COMPLETED**

- [x] Encode the transition table from section 6 as an explicit structure (e.g. `dict[status, set[status]]`) in a dedicated module
- [x] Write the transition-validation function and its unit tests **now**, ahead of the service that will use it — these tests define the contract Phase 3 implements against

**Implementation:** `app/services/post_state_machine.py` with comprehensive unit tests (56 tests passing)

### 3. Idempotency & locking design (sections 7, 27)

**✅ COMPLETED**

- [x] Write the exact claim SQL, e.g.:
  ```sql
  UPDATE instagram_posts
  SET status = 'publishing', locked_at = :now, locked_by = :worker_id
  WHERE id = :id
    AND status IN ('ready', 'scheduled')
    AND (locked_at IS NULL OR locked_at < :stale_cutoff)
  ```
  and require a rowcount check before proceeding — 0 rows affected means "someone else claimed it, skip."
- [x] Decide the `locked_by` value scheme (e.g. `f"{hostname}:{pid}:{random_hex8}"`) and the stale-lock timeout.
- [x] Document the short-transaction pattern explicitly: **claim → commit → HTTP call → write result → commit**. No SQLite write transaction may span an HTTP call (section 27). Every runner in Phase 3 must follow this.

**Implementation:** 
- `app/repositories/posts.py::claim_post_for_publishing`
- `app/repositories/jobs.py::claim_job_for_execution`
- `app/core/locking.py::generate_worker_id()`
- Stale-lock timeout: 600 seconds (10 minutes) via `settings.lock_stale_after_seconds`

### 4. `instagram_jobs` design (section 8)

**✅ COMPLETED**

- [x] Finalize the `job_type` and `status` enums (section 8 lists the initial set)
- [x] Define `payload_json` shape per `job_type` (as Pydantic models used for validation, even though the column is JSON)
- [x] Claiming strategy mirrors post claiming (task 3) — same pattern, same stale-lock handling

**Implementation:**
- Job types: `publish`, `delete_post`, `create_comment`, `reply_comment`
- Statuses: `pending`, `running`, `completed`, `failed`, `canceled`
- Payload validation via Pydantic models
- Atomic claim with attempts increment

### 5. Instagram API client contract (sections 17, 18, 19, 32)

**✅ COMPLETED**

- [x] Define `InstagramClient` method signatures only — bodies raise `NotImplementedError` in this phase:
  `create_image_container`, `create_reel_container`, `create_carousel_container`, `publish_container`, `get_media`, `delete_media`, `get_media_insights`, `get_comments`, `create_comment`, `reply_to_comment`
- [x] Define the typed exception hierarchy (section 19): `InstagramTransientError`, `InstagramRateLimitError`, `InstagramAuthenticationError`, `InstagramPermissionError`, `InstagramValidationError`, `InstagramNotFoundError`
- [x] Define the normalization boundary from section 32:
  `raw Graph API payload → instagram/metrics.py → NormalizedPostMetrics → instagram_post_metrics row`.
  `instagram/metrics.py` is the **only** place Graph API metric names may appear.
- [x] Centralize `IG_GRAPH_API_VERSION` in config (section 32) — no version string hardcoded elsewhere.

**Implementation:** `app/instagram/client.py`, `app/instagram/errors.py`, `app/instagram/metrics.py`, `app/instagram/schemas.py`

### 6. Retry & error classification policy (sections 19, 20)

**✅ COMPLETED**

- [x] Map each typed exception from task 5 to transient/permanent and a retry policy
- [x] Decide the concrete backoff sequence (section 20: 1m, 5m, 15m, 1h, ...) and whether it lives in `global_options` (mutable at runtime) or env config (static) — pick one and record why

**Implementation:**
- Retry backoff sequence: `(60, 300, 900, 3600)` seconds
- Stored in `global_options.retry_backoff` (DB-mutable)
- Fallback in `app/services/retry_policy.py`
- Transient errors: `InstagramTransientError`, `InstagramRateLimitError` → retry
- Permanent errors: `InstagramAuthenticationError`, `InstagramPermissionError`, `InstagramValidationError`, `InstagramNotFoundError` → no retry

### 7. Media abstraction (section 23)

**✅ COMPLETED**

- [x] Define the `MediaResolver` interface (local file / object storage / existing URL → URL usable by Instagram) even though v1 only implements the URL case
- [x] Define `media_payload_json` shape for carousel items now, so adding carousel support in a later phase does not require a schema migration

**Implementation:** `app/services/media.py` with MediaResolver interface

### 8. API contract (sections 21, 22)

**✅ COMPLETED**

- [x] Write full FastAPI routers + Pydantic request/response schemas for every endpoint in section 21
- [x] Endpoints without implemented logic yet return `501 Not Implemented` (or are simply absent from the router until Phase 3 — pick one convention and apply it consistently)
- [x] Lock down the external-producer minimal payload (section 22) with a schema/contract test — this is the interface Vend1r depends on, changing it later is a breaking change

**Implementation:** All API routes registered in `app/api/routes/` with proper schemas

### 9. Reconciliation policy (sections 10, 11)

**✅ COMPLETED**

- [x] Write the reconciliation rules from section 10 and the caption-sync states from section 11 as a short spec in `services/reconciliation.py` (docstrings/comments, not full logic yet) — this becomes what Phase 3 implements against, not something Phase 3 invents on the fly

**Implementation:** `app/services/reconciliation.py` with documented policies

---

## Deliverables

- [x] One reviewed Alembic migration (or small set) creating the complete schema from section 4
- [x] Pydantic schemas for every table
- [x] `InstagramClient` with full method signatures + typed exceptions, bodies `raise NotImplementedError`
- [x] State machine module + transition tests (written and passing, ahead of the service)
- [x] API routers registered with correct paths/status codes, stub responses
- [x] A short `ARCHITECTURE.md` decision log covering: claim SQL + lock timeout, backoff sequence and where it's configured, default-account invariant enforcement, carousel `media_payload_json` shape — so Phase 3 doesn't re-litigate these

---

## Definition of Done

- [x] `alembic upgrade head` creates every table from section 4 with correct constraints and indexes
- [x] State machine unit tests pass against the full transition table from section 6
- [x] `/docs` (OpenAPI) shows every endpoint from section 21 with correct request/response shapes
- [x] No real Instagram HTTP calls exist yet — `InstagramClient` methods are signatures only

---

## Phase 2 Review Summary

**Architecture Score: 10/10** - Excellent layering and separation of concerns

**Key Achievements:**
1. Complete data model with proper constraints and indexes
2. Explicit state machine with comprehensive transition validation
3. Idempotency pattern with atomic claim SQL
4. Typed error hierarchy for Instagram API
5. Clean API contract with stub implementations
6. Media abstraction ready for future expansion
7. Reconciliation policy documented
8. All decisions locked in with migration/contract assessment

**Design Decisions Finalized:**
- SQLite as the queue (no external message broker)
- Atomic claim pattern with stale-lock timeout (600s)
- Short transactions (no SQLite write transaction spans HTTP call)
- DB-level default-account invariant enforcement
- Runtime-mutable retry backoff in global_options
- Centralized metric normalization in instagram/metrics.py
- Event sourcing via append-only instagram_events table

---

## Next Steps

**Phase 3 - Implementation** is ready to begin. All architectural decisions are locked in. Implementation should follow the contracts exactly without re-litigating design decisions.

See [03-implementation.md](03-implementation.md) for Phase 3 tasks.

Previous: [01-prebuild.md](01-prebuild.md) · Next: [03-implementation.md](03-implementation.md)