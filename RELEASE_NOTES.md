# AnnaPost 0.1.1

## Highlights

- Fixes Instagram media synchronization by requesting required Insight metrics
  individually and aggregating the responses.
- Isolates test media and SQLite state from the live workspace.
- Adds concise operational and coding-agent documentation.

## Verification

151 tests, Ruff, formatting, `/health`, and an authenticated sync of an
already-published Instagram post passed on 2026-08-19. No draft was published.
