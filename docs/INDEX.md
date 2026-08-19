# AnnaPost developer index

Current documentation for developers and coding agents. Source code, schemas,
and tests override prose when they disagree.

| To work on | Read first | Then inspect |
| --- | --- | --- |
| Local setup, tests, or server operation | [QUICKSTART.md](QUICKSTART.md) | `pyproject.toml`, `Makefile`, `app/main.py` |
| A publish, retry, deletion, comment, or sync | [OPERATIONS.md](OPERATIONS.md) | `app/services/`, `app/runners/`, `app/instagram/client.py` |
| Domain model, API, or state transition | [../ARCHITECTURE.md](../ARCHITECTURE.md) | `app/db/models/`, `app/api/routes/`, `app/schemas/` |
| Test fixtures or network boundaries | [../../TESTING.md](../../TESTING.md) | `tests/conftest.py`, the relevant test module |

Do not publish, delete remote media, or send a comment merely to test a path.
Each is a real Instagram write and needs a reviewed target and explicit
confirmation. The normal live-safe check is an authenticated sync of an
already-published post.

Freshness: verified against source and a successful authenticated sync on
2026-08-19.
