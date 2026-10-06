# AI-assisted QA workflow

The project uses the approach from [`herchila/unittest-ai-agent`](https://github.com/herchila/unittest-ai-agent) as an optional development aid, not as a runtime dependency. Generated tests must be reviewed and run before they are committed.

For a local generation pass, install the tool in a separate Poetry environment and point it at the backend source:

```bash
poetry install
poetry run ut generate application/backend/questioning.py
```

Review generated tests for these required classes of behavior before accepting them:

- provider timeouts and malformed responses;
- rate-limit behavior;
- unsupported questions and empty evidence;
- read-only SQL rejection;
- audience isolation and concurrent request ordering;
- SQLite and PostgreSQL compatibility.

Run the checked-in suite with:

```bash
PYTHONPATH=application pytest -q application/backend
```

The PostgreSQL compatibility test is skipped unless `DATABASE_URL` points to an isolated test database that has been migrated with the synthetic schema. Never point automated tests at the live production database.
