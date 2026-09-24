# Books API (FastAPI)

Backend for the books assignment. The full design is in [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md). Section 2 of that file is the API contract shared with `client/`.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup and run

```bash
cd server
uv sync
cp .env.example .env
uv run python -m app                    # http://localhost:4000/api/v1
```

For development with auto-reload:

```bash
uv run uvicorn app.main:create_app --factory --reload --port 4000
```

Interactive docs are served at `http://localhost:4000/docs` unless `APP_ENV=production`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness |
| `POST` | `/api/v1/books` | Add a book `{ title, author?, status? }` |
| `GET` | `/api/v1/books?status=reading` | List books, optional status filter |
| `GET` | `/api/v1/books/stats` | Count by status + total |
| `PATCH` | `/api/v1/books/{id}` | Change status `{ status }` |

## Checks

```bash
uv run pytest          # tests
uv run ruff check .    # lint (includes bandit security rules)
uv run mypy            # strict type check
uv run pip-audit       # known-vulnerability scan of dependencies
```

## Red → green demo

The status-filter test was written before the filter existed. The git history shows it: `create + list`, then `add status filter test (failing)`, then `filter list by status`.

To replay the failure and the fix on screen, start from a clean working tree. The checkout below overwrites uncommitted changes in `app/`.

```bash
git status --short app                      # must print nothing

# RED: app code from before the fix, current tests
git checkout ':/add status filter test' -- app
uv run pytest tests/test_books_list.py      # 4 filter tests fail, e.g. "assert 3 == 2"

# GREEN: restore the fixed app code
git checkout HEAD -- app
uv run pytest tests/test_books_list.py      # 7 passed
```

## Configuration

All settings come from environment variables or `.env`. See `.env.example`. Invalid values stop the server at startup.

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `production` disables `/docs` and `/openapi.json` |
| `PORT` | `4000` | |
| `DB_PATH` | `./data/books.db` | SQLite file, created on first run |
| `CORS_ORIGIN` | `http://localhost:5173` | Comma-separated allowlist |
| `TRUST_PROXY` | `false` | Set `true` only behind a known reverse proxy |
| `RATE_LIMIT_MAX` / `RATE_LIMIT_WINDOW_MS` | `100` / `900000` | Per IP, all `/api` requests |
| `WRITE_RATE_LIMIT_MAX` / `WRITE_RATE_LIMIT_WINDOW_MS` | `20` / `60000` | Per IP, `POST` and `PATCH` |
| `RATE_LIMIT_DISABLED` | `false` | Tests only |
| `JSON_BODY_LIMIT` | `10kb` | Larger bodies get `413` |
