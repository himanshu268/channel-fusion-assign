# Books API — Backend Technical Specification (Python / FastAPI)

> Scope: backend only. The frontend has its own spec at `client/TECHNICAL_SPEC.md`.
> Section 2 ("Integration Contract") is duplicated verbatim in both specs. If you change it here, change it there too.

---

## 0. Assignment (source of truth)

- **API** — add a book (`title`, `author`, `status`: `to-read` / `reading` / `done`), list books filterable by status, one aggregation (count by status).
- **Validation** — `title` required; `status` must be one of the three values.
- **Tests** — cover add, list, filter. At least one test must fail first, then be fixed on screen (red → green).
- **Non-functional** — OWASP Top 10 (2021) mitigations, rate limiting.

---

## 1. Stack & decisions

| Concern | Choice | Why |
|---|---|---|
| Runtime | Python 3.12 | Current stable, modern typing (`X \| None`, `Annotated`) |
| Framework | FastAPI (Starlette 1.x) | Pydantic-native validation, dependency injection, async-capable, auto OpenAPI in dev |
| Package / env | `uv` + `pyproject.toml` + `uv.lock` | Fast, reproducible installs with a committed lockfile (A06/A08) |
| Validation | Pydantic v2 | One model gives runtime validation, custom messages, `extra="forbid"` |
| Config | `pydantic-settings` | Typed env parsing; invalid env fails fast at startup |
| DB | SQLite via stdlib `sqlite3` | Zero infra, `:memory:` for tests. Repository `Protocol` keeps a Postgres swap trivial |
| Security headers | Custom `CoreMiddleware` | Helmet-equivalent header set, tuned for a JSON-only API |
| CORS | Starlette `CORSMiddleware`, explicit allowlist | A01/A05 |
| Rate limiting | Custom in-memory fixed-window limiter | Exact contract headers (`RateLimit-*`, `Retry-After`), no extra deps, Redis-swappable |
| Logging | stdlib `logging` + JSON formatter | Structured logs with request id (A09), no extra deps |
| Server | `uvicorn` | `server_header=False` hides the server banner, like disabling `x-powered-by` |
| Tests | pytest + FastAPI `TestClient` (`httpx2`) | In-process app, no port binding |
| Quality | ruff (incl. bandit `S` rules), mypy `--strict` + pydantic plugin, pip-audit | Lint, types, dependency CVEs |

**Explicit non-goals:** authentication/authorization (no users in scope, see A01/A07), pagination, soft delete, DELETE endpoint.

---

## 2. Integration Contract (shared — identical in both specs)

### 2.1 Networking

| Item | Value |
|---|---|
| Backend port | `4000` (env `PORT`) |
| Frontend dev port | `5173` (Vite) |
| API prefix | `/api/v1` |
| Dev CORS | Vite proxies `/api/*` → `http://localhost:4000`; browser sees same-origin, no CORS in dev |
| Prod CORS | Backend allowlist from env `CORS_ORIGIN` (comma-separated). Methods `GET,POST,PATCH`. Allowed request headers `Content-Type`, `X-Request-Id`. Exposed response headers `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, `Retry-After`, `X-Request-Id`. No credentials |
| Content type | Requests with a body MUST send `Content-Type: application/json`, else `415` |
| Request ID | Backend sets/echoes `X-Request-Id` on every response; frontend may send one |

### 2.2 Data model

```ts
type BookStatus = 'to-read' | 'reading' | 'done';

interface Book {
  id: string;         // UUID v4
  title: string;      // 1..200 chars, trimmed
  author: string;     // 0..200 chars, trimmed; '' when not given
  status: BookStatus; // default 'to-read'
  createdAt: string;  // ISO 8601 UTC
  updatedAt: string;  // ISO 8601 UTC
}

interface BookStats {
  'to-read': number;
  reading: number;
  done: number;
  total: number;
}
```

### 2.3 Response envelope

Every JSON response is one of:

```jsonc
// success
{ "data": <Book | Book[] | BookStats | { "status": "ok" }> }

// error
{
  "error": {
    "code": "VALIDATION_ERROR" | "NOT_FOUND" | "UNSUPPORTED_MEDIA_TYPE" | "PAYLOAD_TOO_LARGE" | "RATE_LIMITED" | "INTERNAL_ERROR",
    "message": "human readable, safe to show to user",
    "details": [ { "path": "title", "message": "Title is required" } ] // only for VALIDATION_ERROR
  }
}
```

### 2.4 Endpoints

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| `GET` | `/api/v1/health` | — | `200 { data: { status: "ok" } }` | — |
| `POST` | `/api/v1/books` | `{ title: string, author?: string, status?: BookStatus }` | `201 { data: Book }` | `400`, `413`, `415`, `429` |
| `GET` | `/api/v1/books` | query `?status=to-read\|reading\|done` (optional) | `200 { data: Book[] }` sorted `createdAt DESC` | `400` (bad status), `429` |
| `GET` | `/api/v1/books/stats` | — | `200 { data: BookStats }` | `429` |
| `PATCH` | `/api/v1/books/:id` | `{ status: BookStatus }` | `200 { data: Book }` | `400`, `404` (unknown or malformed id), `413`, `415`, `429` |

Validation rules (identical client + server):
- `title`: required, string, trimmed, length 1–200. Empty/whitespace-only → `400` with `details[{path:"title"}]`.
- `author`: optional, string, trimmed, length ≤ 200.
- `status`: optional on create (default `to-read`), required on PATCH; must be one of the three literals.
- Unknown body fields → **rejected** (`400`), Zod `.strict()`.
- `?status=` repeated: every value must be valid and all values the same, else `400` (`Status must be given once` when they conflict).
- Text cleaning (title, author): trim; strip C0/C1 control chars, U+2028/2029, bidi marks/overrides/isolates, zero-width space, BOM. ZWJ/ZWNJ kept inside text. Invisible-only input counts as empty.
- Trailing slash (`/api/v1/books/`) → `404 NOT_FOUND` JSON, never a redirect.
- Unknown query params → ignored.

### 2.5 Rate limiting (visible to the frontend)

| Limiter | Scope | Default | Env |
|---|---|---|---|
| Global | all `/api/*` except `/api/v1/health`, per IP | 100 req / 15 min | `RATE_LIMIT_WINDOW_MS`, `RATE_LIMIT_MAX` |
| Write | `POST`, `PATCH` under `/api/*`, per IP | 20 req / 1 min | `WRITE_RATE_LIMIT_WINDOW_MS`, `WRITE_RATE_LIMIT_MAX` |

On every response: `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` (IETF RateLimit header fields, draft-06 naming; `RateLimit-Reset` = seconds until window resets).
On `429`: additionally `Retry-After: <seconds>` and body `{ error: { code: "RATE_LIMITED", message: "Too many requests, try again in N seconds" } }`.
Frontend MUST honour `Retry-After` (disable the action, show countdown).

### 2.6 Example exchanges

```http
POST /api/v1/books
Content-Type: application/json

{ "title": "Dune", "author": "Frank Herbert" }

HTTP/1.1 201 Created
{ "data": { "id": "6f1c…", "title": "Dune", "author": "Frank Herbert", "status": "to-read", "createdAt": "2026-09-24T10:00:00.000Z", "updatedAt": "2026-09-24T10:00:00.000Z" } }
```

```http
POST /api/v1/books
{ "title": "   ", "status": "finished" }

HTTP/1.1 400 Bad Request
{ "error": { "code": "VALIDATION_ERROR", "message": "Invalid request body",
  "details": [ { "path": "title", "message": "Title is required" },
               { "path": "status", "message": "Status must be one of: to-read, reading, done" } ] } }
```

```http
GET /api/v1/books/stats

HTTP/1.1 200 OK
{ "data": { "to-read": 3, "reading": 1, "done": 2, "total": 6 } }
```

---

## 3. Project layout

```
server/
├── pyproject.toml             # deps, ruff, mypy, pytest config
├── uv.lock                    # committed lockfile
├── .env.example
├── README.md
├── data/                      # SQLite file (gitignored)
├── app/
│   ├── __main__.py            # `python -m app`: Settings() → create_app → uvicorn.run
│   ├── main.py                # create_app(settings, conn, clock): error handlers, routes, middleware. No listen
│   ├── core/
│   │   ├── config.py          # Settings (pydantic-settings), body_limit_bytes, cors_origins
│   │   ├── errors.py          # HttpError, error_body(), error_response() envelope helpers
│   │   └── logging.py         # JSON formatter, configure_logging(), `books` logger
│   ├── db/
│   │   ├── connection.py      # open_db(path | ':memory:'), WAL + foreign_keys pragmas
│   │   └── migrate.py         # idempotent CREATE TABLE IF NOT EXISTS + indexes
│   ├── middleware/
│   │   ├── core.py            # request id, security headers, Cache-Control, 500 boundary, access log
│   │   ├── cors.py            # JsonCORSMiddleware: rejected preflight → JSON envelope, not text/plain
│   │   ├── rate_limit.py      # FixedWindowLimiter, client_ip(), RateLimitMiddleware (global + write)
│   │   └── body_guard.py      # pure ASGI: 415 non-JSON body, 413 oversized body (incl. chunked)
│   └── modules/books/
│       ├── schemas.py         # BookStatus, Book, BookStats, CreateBookIn, UpdateStatusIn
│       ├── repository.py      # BookRepository Protocol + SqliteBookRepository (parameterised SQL)
│       ├── service.py         # BookService: create, list(status), update_status, stats. Injectable clock
│       └── router.py          # APIRouter, list_query() dependency, Annotated deps
└── tests/
    ├── conftest.py            # make_client(**settings), FakeClock, client / add_book fixtures
    ├── test_books_create.py
    ├── test_books_list.py     # contains the scripted red → green test
    ├── test_books_stats.py
    ├── test_books_update.py
    ├── test_security.py       # headers, CORS, 404/413/415/500 envelopes, rate limits, docs off in prod
    ├── test_validation_edge_cases.py  # boundaries, types, unicode hardening, media types, size limit, PATCH ids
    └── test_contract_and_limits.py    # envelope on every path, CORS, rate-limit interplay, config, concurrency
```

### 3.1 Dependencies

```bash
uv venv --python 3.12
uv add fastapi "uvicorn[standard]" pydantic pydantic-settings
uv add --dev pytest httpx2 mypy ruff pip-audit
```

### 3.2 Commands

| Task | Command |
|---|---|
| Install | `uv sync` |
| Run | `uv run python -m app` (reads `.env`, port `4000`) |
| Dev with reload | `uv run uvicorn app.main:create_app --factory --reload --port 4000` |
| Test | `uv run pytest` |
| Lint / format | `uv run ruff check .` · `uv run ruff format .` |
| Typecheck | `uv run mypy` |
| Audit | `uv run pip-audit` |

### 3.3 Environment (`.env.example`)

```env
APP_ENV=development          # development | test | production (production disables /docs and /openapi.json)
PORT=4000
LOG_LEVEL=info               # debug | info | warning | error
DB_PATH=./data/books.db
CORS_ORIGIN=http://localhost:5173
TRUST_PROXY=false
RATE_LIMIT_WINDOW_MS=900000
RATE_LIMIT_MAX=100
WRITE_RATE_LIMIT_WINDOW_MS=60000
WRITE_RATE_LIMIT_MAX=20
RATE_LIMIT_DISABLED=false
JSON_BODY_LIMIT=10kb         # 2048 | 10kb | 1mb
```

`core/config.py` parses this with pydantic-settings and **fails fast** on startup if a value is invalid.

---

## 4. Database

```sql
CREATE TABLE IF NOT EXISTS books (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  author      TEXT NOT NULL DEFAULT '' CHECK (length(author) <= 200),
  status      TEXT NOT NULL CHECK (status IN ('to-read','reading','done')),
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);
CREATE INDEX IF NOT EXISTS idx_books_created_at ON books(created_at DESC);
```

- DB-level `CHECK` constraints are defence in depth behind Pydantic.
- One shared connection (`check_same_thread=False`, autocommit). The repository serialises access with a `threading.Lock`, because FastAPI runs sync endpoints in a threadpool.
- The list query orders by `created_at DESC, rowid DESC`, so rows created in the same millisecond stay in a stable order.
- Stats query: `SELECT status, COUNT(*) AS n FROM books GROUP BY status`. The service fills missing statuses with `0`, so the shape is always complete.
- Timestamps come from an injectable clock and are formatted as ISO 8601 UTC with milliseconds and `Z`. Tests use a fake clock.

```python
class BookRepository(Protocol):
    def insert(self, book: Book) -> Book: ...
    def find_all(self, status: BookStatus | None = None) -> list[Book]: ...
    def find_by_id(self, book_id: str) -> Book | None: ...
    def update_status(self, book_id: str, status: BookStatus, updated_at: str) -> Book | None: ...
    def count_by_status(self) -> dict[BookStatus, int]: ...
```

All SQL uses `?` placeholders. **Never** interpolate values into SQL strings.

---

## 5. Request pipeline (outer → inner)

```
CoreMiddleware        request id (validated), try/except → 500 envelope, security headers, access log
→ JsonCORSMiddleware  allowlist, GET/POST/PATCH, exposes RateLimit-*/Retry-After/X-Request-Id; rejected preflight → 400 JSON
→ RateLimitMiddleware /api/* only, skips OPTIONS. Global limiter, then write limiter for POST/PATCH
→ BodyGuardMiddleware 415 if a body is present and not application/json. 413 if > JSON_BODY_LIMIT
→ routes
     GET   /api/v1/health          (GET + HEAD, HEAD hidden from OpenAPI; exempt from rate limiting)
     GET   /api/v1/books/stats     registered before /{book_id}
     GET   /api/v1/books           list_query() dependency validates ?status=
     POST  /api/v1/books           body: CreateBookIn
     PATCH /api/v1/books/{book_id} body: UpdateStatusIn. Non-UUID id → 404
```

Starlette's `add_middleware` makes the last-added middleware the outermost, so `create_app` adds them in reverse order. `CoreMiddleware` is outermost, so every response gets security headers and a request id, including 429, 413, 415 and 500.

### 5.1 Error mapping

| Incoming | Response |
|---|---|
| `HttpError` | its status + `{ error: { code, message, details? } }` |
| `RequestValidationError` | `400 VALIDATION_ERROR`, message `Invalid request body`, `details[{path, message}]` |
| … with `json_invalid` | message `Malformed JSON` |
| … with `extra_forbidden` | detail message `Unknown field` |
| … body missing / not an object | detail message `Request body is required` / `Request body must be a JSON object` |
| Invalid `?status=` | `400 VALIDATION_ERROR`, message `Invalid query parameters` |
| Starlette 404 / 405 | `404 NOT_FOUND`, message `Route not found` (never HTML). `redirect_slashes=False`, so a trailing slash is a 404 too |
| Rejected CORS preflight | `400 VALIDATION_ERROR`, message `Disallowed CORS origin` / `method` / `headers` |
| Oversized body | `413 PAYLOAD_TOO_LARGE` (from BodyGuard) |
| Any other exception | `500 INTERNAL_ERROR`, `Something went wrong`. Traceback logged server-side with request id, never sent |

Custom field messages (`Title is required`, `Status must be one of: to-read, reading, done`, and others) are raised with `PydanticCustomError` in `mode="before"` validators. Required fields use `default=None, validate_default=True`, so a missing field reaches the custom message too.

---

## 6. Security — OWASP Top 10 (2021) mapping

| # | Risk | Mitigation in this service | Where |
|---|---|---|---|
| A01 | Broken Access Control | No auth in scope (single-user assignment), documented. CORS allowlist. Only `GET/POST/PATCH` exposed, others → 404. `TRUST_PROXY` off by default, so `X-Forwarded-For` cannot spoof the client IP. | `main.py`, `rate_limit.py` |
| A02 | Cryptographic Failures | No secrets or PII stored. HSTS header (effective over TLS). `.env` gitignored. TLS terminated at a reverse proxy in prod. | `core.py`, `.gitignore` |
| A03 | Injection | Pydantic validation (types, lengths, enum). Parameterised SQL only. Control, bidi and zero-width characters stripped. JSON-only responses, no templating. Tested with SQL-injection strings in body, query and path. | `schemas.py`, `repository.py` |
| A04 | Insecure Design | Global + stricter write rate limits. Body cap `10kb`, enforced for chunked bodies too. Server-generated UUIDs. Enum allowlist. Fail-fast config. | `rate_limit.py`, `body_guard.py` |
| A05 | Security Misconfiguration | Helmet-equivalent headers: CSP `default-src 'none'`, `nosniff`, `X-Frame-Options DENY`, `Referrer-Policy no-referrer`, HSTS, COOP/CORP. No `server` banner. `/docs` and `/openapi.json` disabled in production. JSON 404/405. No stack traces. | `core.py`, `main.py`, `__main__.py` |
| A06 | Vulnerable & Outdated Components | `uv.lock` committed. `uv run pip-audit` (clean at time of writing). Minimal dependency set. | `pyproject.toml` |
| A07 | Identification & Auth Failures | N/A, no accounts. Extension point: add a router-level `Depends(auth)` on the books router. | this doc |
| A08 | Software & Data Integrity | Lockfile + `uv sync --frozen` in CI. No `eval`/`exec`/`pickle`. `extra="forbid"` blocks mass assignment. DB `CHECK` constraints. | `schemas.py`, `migrate.py` |
| A09 | Security Logging & Monitoring | One JSON log line per request with `request_id`, method, path, status, latency, ip. `400/413/415/429` at `warning`, `500` at `error` with traceback. Incoming `X-Request-Id` accepted only if it matches `^[A-Za-z0-9._-]{1,64}$`, which blocks log injection. | `core.py`, `logging.py` |
| A10 | SSRF | The service makes **no outbound HTTP requests** and accepts no URL fields. | by design |

Additional hardening: `Cache-Control: no-store` on all responses. ruff `S` (bandit) rules run in lint.

---

## 7. Rate limiting — implementation detail

- `FixedWindowLimiter(limit, window_ms, now=time.monotonic)` keeps `key → (window_start, count)` under a lock. `hit(key)` returns `allowed`, `limit`, `remaining` and `reset_seconds`. Expired windows are pruned once the map passes 10k keys.
- `RateLimitMiddleware` applies to paths under `/api` and skips `OPTIONS` preflights. The global limiter runs first. For `POST`/`PATCH`, the write limiter runs next, and its headers win.
- Allowed responses get `RateLimit-Limit`, `RateLimit-Remaining` and `RateLimit-Reset`. Blocked requests get `429`, the same headers plus `Retry-After`, and the `RATE_LIMITED` envelope. Both `Retry-After` and the message use the real seconds left in the window.
- Client IP is `request.client.host`. With `TRUST_PROXY=true`, it is the **last** `X-Forwarded-For` entry, the one appended by our own single proxy.
- For multiple instances, replace `FixedWindowLimiter` with a Redis-backed class with the same `hit()` signature.
- Tests: the default test client sets `RATE_LIMIT_DISABLED=true`. `test_security.py` builds clients with small limits to assert the 429 path, write-vs-read separation, spoofing resistance, and window reset (fake clock).

---

## 8. Testing plan

`make_client(**overrides)` builds `create_app(Settings(APP_ENV="test", RATE_LIMIT_DISABLED=True, ...), open_db(":memory:"), FakeClock())` for each test. `FakeClock` advances 1s per call, so `updatedAt > createdAt` is deterministic.

| File | Cases |
|---|---|
| `test_books_create.py` | 201 + full Book shape (UUID v4, ISO timestamps); defaults `to-read` / `''`; trimming and control-char strip; persisted; title missing / empty / whitespace / null → `Title is required`; > 200; non-string; author > 200; invalid status variants; multiple errors at once; unknown fields rejected; malformed JSON; non-object JSON; 415; `charset` accepted |
| `test_books_list.py` | empty; newest first; **filter by status (red → green)**; each status; no matches; invalid `?status=` (incl. SQL-ish) → 400; unknown query params ignored |
| `test_books_stats.py` | all zeros; correct counts + total; keys always present; reflects status change |
| `test_books_update.py` | status change + `updatedAt` bump, other fields unchanged; 404 unknown UUID; 404 malformed ids; invalid status; missing status; extra fields; no body |
| `test_security.py` | security headers (incl. on errors), no `server` banner, HEAD health, request id generate / echo / sanitise, JSON 404 for unknown route and method, 413 (plain + chunked), SQL injection stored as text, 500 hides details, CORS allow / deny / exposed headers, docs off in prod, global + write rate limits, XFF ignored, window reset |

| `test_validation_edge_cases.py` | length boundaries (chars not bytes, after trim); wrong JSON types per field; exact status literals; unicode control/bidi/zero-width stripping, ZWJ kept; 415 for each non-JSON type; body exactly at / over limit; repeated `?status=`; PATCH id forms, no side effects on rejection |
| `test_contract_and_limits.py` | error envelope on every endpoint and error kind; trailing slash → JSON 404; JSON preflight rejection; timestamps / UUID v4; stats vs list consistency; 429 keeps security + CORS headers; health not rate limited; trusted-proxy XFF; unique OpenAPI operation ids; config fail-fast; 8-thread concurrent writes |

Current result: **214 passed**.

### 8.1 Scripted red → green (done, visible in git history)

| Commit | State |
|---|---|
| `feat(books): create + list` | List endpoint ignores `?status=` |
| `test(books): add status filter test (failing)` | `test_list_filters_by_status` fails: `AssertionError: assert 3 == 2` |
| `feat(books): filter list by status` | `list_query()` dependency + `service.list(status)`. All green |

The test:

```python
def test_list_filters_by_status(client: TestClient, add_book: AddBook) -> None:
    add_book("A", status="reading")
    add_book("B", status="done")
    add_book("C", status="reading")
    res = client.get(f"{URL}?status=reading")
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 2
    assert all(b["status"] == "reading" for b in data)
```

Replaying it on screen is described in `README.md`.

---

## 9. Build order (session checklist)

1. `uv venv --python 3.12`, `pyproject.toml`, deps, `.env.example`, `.gitignore`. ✅
2. `core/config.py`, `core/logging.py`, `core/errors.py`. ✅
3. `db/connection.py`, `db/migrate.py`. ✅
4. `modules/books/schemas.py` (types copied from §2.2). ✅
5. `repository.py`. ✅
6. `middleware/` (core, rate_limit, body_guard). ✅
7. `main.py` (`create_app`), `__main__.py`. ✅
8. `service.py`, `router.py`: create + list first, no filter. ✅
9. `conftest.py`, create + list tests, then the red → green script (§8.1). ✅
10. Stats and `PATCH /{book_id}` with their tests. ✅
11. `test_security.py`. Verify headers with `curl -I`. ✅
12. `ruff check`, `ruff format`, `mypy`, `pytest`, `pip-audit`. ✅
13. Curl smoke (§10), then hand off to the frontend session. ✅

---

## 10. Manual smoke (curl)

```bash
uv run python -m app &
B=localhost:4000/api/v1
curl -s $B/health
curl -s -X POST $B/books -H 'Content-Type: application/json' -d '{"title":"Dune","author":"Frank Herbert"}'
curl -s "$B/books?status=to-read"
curl -s $B/books/stats
curl -s -X PATCH $B/books/<id> -H 'Content-Type: application/json' -d '{"status":"reading"}'
curl -s -X POST $B/books -H 'Content-Type: application/json' -d '{"title":"","status":"nope"}'   # 400
curl -s -X POST $B/books -d 'title=x'                                                            # 415
for i in $(seq 1 25); do curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/books -H 'Content-Type: application/json' -d '{"title":"x"}'; done | sort | uniq -c   # some 429
curl -sI $B/health | grep -iE 'server|content-security-policy|x-content-type-options|ratelimit|x-request-id'
```

---

## 11. Definition of done

- [x] All endpoints in §2.4 return exactly the envelope in §2.3.
- [x] Validation rules in §2.4 enforced. DB `CHECK` constraints present.
- [x] Security headers, CORS allowlist, body limit, no server banner, docs off in prod.
- [x] Global + write rate limiters with `RateLimit-*` headers and `Retry-After`.
- [x] Structured logs with request id. 4xx abuse signals at `warning`, 500 at `error`.
- [x] `uv run pytest` green. Red → green commit history for the filter test.
- [x] `uv run pip-audit` clean. ruff and mypy `--strict` clean.
- [x] `.env.example` complete. `README.md` covers install, run, test and env.
- [ ] Frontend session runs against this server via the Vite proxy with zero backend changes. Pending the frontend build.
