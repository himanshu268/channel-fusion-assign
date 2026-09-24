# Books

A small reading-list app. You can add books, filter them by status (`to-read`, `reading`, `done`), change a book's status, and see how many books have each status.

| Part | Stack | Docs |
|---|---|---|
| [`server/`](server/) | FastAPI, SQLite, Python 3.12 | [README](server/README.md) · [spec](server/TECHNICAL_SPEC.md) |
| [`client/`](client/) | React 18, Vite, TanStack Query, Zod | [README](client/README.md) · [spec](client/TECHNICAL_SPEC.md) |

## Quick start with Docker (recommended)

Requires [Docker](https://docs.docker.com/get-docker/) with Compose v2.

```bash
docker compose up --build
```

Once it is up:

- App: http://localhost:8080
- Swagger docs: http://localhost:8080/docs
- Health check: http://localhost:8080/api/v1/health

One container runs both parts. nginx on port 8080 serves the UI and forwards `/api/*` to the API. The API listens only inside the container, so the browser sees a single origin and no CORS setup is needed. Books are stored in the `books-data` volume, so they survive restarts.

```bash
docker compose down        # stop (keeps data)
docker compose down -v     # stop and delete the database
```

### Run the tests in Docker

```bash
docker compose --profile test run --rm api-test   # ruff + mypy + pytest
docker compose --profile test run --rm ui-test    # eslint + tsc + vitest
```

Neither test suite needs a running server. The API tests use in-memory SQLite, and the UI tests mock the API with MSW.

### Without Compose

```bash
docker build -t books .
docker run --rm -p 8080:8080 -v books-data:/data books
```

This uses `APP_ENV=production`, so `/docs` is turned off. Add `-e APP_ENV=development` to turn it back on.

## Try the API

```bash
# add a book
curl -s -X POST http://localhost:8080/api/v1/books \
  -H 'Content-Type: application/json' \
  -d '{"title": "Dune", "author": "Frank Herbert", "status": "reading"}'

# list, optionally filtered by status
curl -s http://localhost:8080/api/v1/books
curl -s 'http://localhost:8080/api/v1/books?status=reading'

# change the status (use the id returned by POST)
curl -s -X PATCH http://localhost:8080/api/v1/books/<id> \
  -H 'Content-Type: application/json' \
  -d '{"status": "done"}'

# count per status
curl -s http://localhost:8080/api/v1/books/stats
```

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness |
| `POST` | `/api/v1/books` | Add a book `{ title, author?, status? }` |
| `GET` | `/api/v1/books?status=` | List books, with an optional status filter |
| `GET` | `/api/v1/books/stats` | Count per status and total |
| `PATCH` | `/api/v1/books/{id}` | Change status `{ status }` |

Successful responses are wrapped as `{ "data": ... }` and errors as `{ "error": { "code", "message", "details"? } }`, where `details` is only present on validation errors. See §2 of [server/TECHNICAL_SPEC.md](server/TECHNICAL_SPEC.md) for the full contract.

## Local development (without Docker)

Requirements: Python 3.12+ with [uv](https://docs.astral.sh/uv/), and Node 20+.

Use two terminals:

```bash
# 1. API → http://localhost:4000
cd server
uv sync
cp .env.example .env
uv run uvicorn app.main:create_app --factory --reload --port 4000
```

```bash
# 2. UI → http://localhost:5173 (Vite forwards /api to :4000)
cd client
npm ci
npm run dev
```

Checks:

```bash
cd server && uv run pytest && uv run ruff check . && uv run mypy
cd client && npm run lint && npm run typecheck && npm test
```

## Configuration

You can override these in the environment or in `docker-compose.yml`:

| Variable | Compose default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `production` turns off `/docs` and `/openapi.json` |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning`, or `error` |
| `RATE_LIMIT_DISABLED` | `false` | Set to `true` to try things without hitting 429s |

Example: `RATE_LIMIT_DISABLED=true docker compose up --build`.

The default limits are 100 requests per 15 minutes and 20 writes per minute, counted per IP. The full list of settings is in [server/README.md](server/README.md#configuration).

## Troubleshooting

- **Port 8080 is already in use.** Change the mapping in `docker-compose.yml` to `"3000:8080"`, for example, and open http://localhost:3000.
- **`429 Too Many Requests`.** You hit the rate limit. Wait for the time in the `Retry-After` header, or restart with `RATE_LIMIT_DISABLED=true`.
- **Container is `unhealthy`.** Run `docker compose logs app`. Invalid settings stop the API at startup, and the error names the setting.
- **You want a clean database.** Run `docker compose down -v`.

## Project layout

```
.
├── Dockerfile            single image: UI build + API + nginx; also api-test / ui-test stages
├── docker-compose.yml    app service + test profile
├── docker/
│   ├── nginx.conf        serves the UI, forwards /api, sets security headers
│   └── start.sh          runs uvicorn and nginx, and exits if either stops
├── server/               FastAPI backend
└── client/               React frontend
```
