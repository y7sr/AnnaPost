# AnnaPost quick start

Run commands from the AnnaPost repository root.

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
.venv/bin/python -m app.main
curl --fail http://127.0.0.1:8000/health
```

The application reads `.env` through `app/core/config.py`. Never print or
commit credential values. The SQLite database and `data/media/` are durable
operational state; tests redirect both into temporary locations.

For managed Instagram work, use the persisted API → job → runner flow. The
`posts publish-file --confirm` command is a one-shot public write, not a smoke
test.
