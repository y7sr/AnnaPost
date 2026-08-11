# Phase 5 — Review

Reference: `plan.annapost.md` sections 29–31, 34, 35; corresponds to old section 33 "Phase 8 — Operational Hardening", extended to cover the UI added in Phase 4.

## Goal

Harden and validate the whole system against the full spec before calling v1 done. Nothing new gets built here beyond what's needed to close gaps found during review.

## Tasks

### 1. Full test suite pass (section 29)
Run every item in section 29's list to completion, including the ones that are easy to skip under time pressure:
- runner crash/restart scenarios (kill a runner mid-claim, rerun, assert no duplicate action)
- SQLite concurrency (multiple runner processes against one DB file, WAL mode, `busy_timeout` actually prevents lock errors under contention)
- Instagram malformed responses (client degrades to a typed exception, doesn't crash the runner)
- expired token behavior (surfaces as `InstagramAuthenticationError`, does not retry forever — section 19/34)

### 2. Structured logging pass (section 30)
- Audit every log call: required fields present (`runner`, `job_id`, `post_id`, `account_id`, `instagram_media_id`, `operation`, `attempt`, `duration`, `result`, `error_type`)
- Confirm no access tokens, secrets, or large raw payloads are logged anywhere — including in the Phase 4 UI request logs
- Confirm `instagram_events` (application history) and logs (operational diagnostics) stay conceptually separate — no log statement is being used as a substitute for an event, and vice versa

### 3. Security review (section 31)
- Access tokens never appear in any API or UI response body
- Secrets live outside source control (`.env`, not committed; `.env.example` has placeholders only)
- External URLs/input are validated before use (media URLs, especially — section 23)
- No arbitrary filesystem access from the media-handling path
- Admin UI (Phase 4) doesn't leak anything the API wouldn't

### 4. Configuration cleanup
- Every setting is either in `global_options` (DB-mutable) or env config (static) — no setting living ambiguously in both, no dead/unused config left over from earlier phases
- `.env.example` matches what `core/config.py` actually reads

### 5. API validation pass
- Pydantic validation failures return clean 4xx bodies, not 500s
- `/docs` (OpenAPI) is accurate for every endpoint — no stale stub descriptions left from Phase 2

### 6. Code review / lint
- `ruff check .` clean
- Remove any dead stub code left over from Phase 2 (`NotImplementedError` bodies, unused stub routers)
- Explicitly check for duplicated Instagram-calling logic across runners (section 34 forbids this) — everything must funnel through `InstagramClient`

### 7. Constraint checklist (section 34)
Walk both lists in section 34 explicitly and confirm each item, don't just assume:

**Do not** (confirm none were violated): coupling to Vend1r, hardcoded single account, Vend1r publishing directly, overwritten historical metrics, missing metrics treated as zero, external HTTP held inside a long SQLite write transaction, duplicated Instagram API logic across runners, permanent errors retried forever, physical deletion of operational history by default, Redis/Celery/etc. added without demonstrated need.

**Do** (confirm each is actually true): API is the integration boundary, runners are independently executable, operations are idempotent, raw Instagram responses preserved where useful, all posts are account-specific, append-only events used for important actions, historical metrics stored, reconciliation supported, system designed around Graph API instability (section 32's normalization boundary is intact, not bypassed anywhere).

### 8. Definition of Done walkthrough (section 35)
Execute the full 16-step flow from section 35 end-to-end one more time, ideally as a scripted integration test rather than a manual click-through, and record the result:
1. Create/configure account → 2. mark default → 3. external client creates image post via API → 4. immediate or scheduled → 5. `publish_runner` publishes exactly once → 6. IDs/permalink/timestamp stored → 7. `sync_runner` fetches metrics → 8. historical snapshots stored → 9. comments imported without duplicates → 10. API queues outgoing comment/reply → 11. `action_runner` sends it and records result → 12. API soft-deletes a published post → 13. `action_runner`/reconciliation removes it remotely → 14. failures produce useful state/retries/events → 15. multiple accounts, no cross-account leakage → 16. full automated suite passes with no real Instagram network calls.

## Deliverables
- Green run: `ruff check .` + full `pytest` with `pytest-cov` coverage report
- Short written sign-off against section 34's Do/Do-not list and section 35's 16-step flow (pass/fail per item, not just "looks fine")

## Definition of Done
Section 35's 16-step flow passes reliably and repeatably, with zero real Instagram network calls in the automated suite, and nothing in section 34's "Do not" list is violated.

Previous: [04-ui.md](04-ui.md)
