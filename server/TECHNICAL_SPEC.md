# Books API — Backend Technical Specification

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
| Runtime | Node 20 LTS | Stable, native `fetch`, wide support |
| Framework | Express 5 | Async error propagation built in, huge middleware ecosystem |
| Language | TypeScript (strict) | Type safety on contract types shared with frontend |
| Validation | Zod | Single schema → runtime validation + inferred TS types |
| DB | SQLite via `better-sqlite3` | Zero infra, synchronous API, `:memory:` for tests. Repository interface keeps Postgres swap trivial |
| Security headers | `helmet` | Sane defaults for A05 |
| CORS | `cors` with explicit allowlist | A01/A05 |
| Rate limiting | `express-rate-limit` v7 | Standard `RateLimit-*` headers, memory store OK for single instance |
| Logging | `pino` + `pino-http` | Structured JSON logs, request IDs (A09) |
| Tests | Vitest + Supertest | Fast, TS native, in-process app (no port binding) |
| Dev runner | `tsx` | No build step during dev |

**Explicit non-goals:** authentication/authorization (no users in scope — documented under A01/A07), pagination, soft delete, DELETE endpoint.

---

## 2. Integration Contract (shared — identical in both specs)

### 2.1 Networking

| Item | Value |
|---|---|
| Backend port | `4000` (env `PORT`) |
| Frontend dev port | `5173` (Vite) |
| API prefix | `/api/v1` |
| Dev CORS | Vite proxies `/api/*` → `http://localhost:4000`; browser sees same-origin, no CORS in dev |
| Prod CORS | Backend allowlist from env `CORS_ORIGIN` (comma-separated). Methods `GET,POST,PATCH`. Headers `Content-Type`. No credentials |
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
- Unknown query params → ignored.

### 2.5 Rate limiting (visible to the frontend)

| Limiter | Scope | Default | Env |
|---|---|---|---|
| Global | all `/api/*`, per IP | 100 req / 15 min | `RATE_LIMIT_WINDOW_MS`, `RATE_LIMIT_MAX` |
| Write | `POST`, `PATCH` under `/api/*`, per IP | 20 req / 1 min | `WRITE_RATE_LIMIT_WINDOW_MS`, `WRITE_RATE_LIMIT_MAX` |

On every response: `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` (draft-7 standard headers).
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
├── package.json
├── tsconfig.json
├── vitest.config.ts
├── .env.example
├── .gitignore                 # node_modules, dist, data/, .env
├── data/                      # SQLite file lives here (gitignored)
├── src/
│   ├── index.ts               # bootstrap only: loadEnv → openDb → migrate → createApp → listen
│   ├── app.ts                 # createApp(deps): wires middleware + routes, NO listen (testable)
│   ├── config/
│   │   └── env.ts             # Zod-validated process.env → typed Config
│   ├── db/
│   │   ├── connection.ts      # openDb(path | ':memory:') with WAL + foreign_keys pragmas
│   │   └── migrate.ts         # idempotent CREATE TABLE IF NOT EXISTS + indexes
│   ├── lib/
│   │   ├── httpError.ts       # class HttpError(status, code, message, details?)
│   │   └── logger.ts          # pino instance, redact config
│   ├── middleware/
│   │   ├── requestId.ts       # X-Request-Id passthrough or randomUUID()
│   │   ├── requireJson.ts     # 415 if body present and content-type != application/json
│   │   ├── validate.ts        # validate({ body?, query?, params? }) → 400 VALIDATION_ERROR
│   │   ├── rateLimit.ts       # globalLimiter, writeLimiter factories (env-driven, disable flag)
│   │   ├── notFound.ts        # 404 NOT_FOUND for unmatched routes
│   │   └── errorHandler.ts    # HttpError → envelope; unknown → 500, log, no stack in prod
│   └── modules/books/
│       ├── book.schema.ts     # BookStatus enum, createBookSchema, updateStatusSchema, listQuerySchema, idParamSchema
│       ├── book.types.ts      # Book, BookStats (inferred from schema / explicit)
│       ├── book.repository.ts # interface BookRepository + SqliteBookRepository (parameterized SQL)
│       ├── book.service.ts    # create, list(filter), updateStatus, stats — throws HttpError(404)
│       ├── book.controller.ts # thin: parse → service → res.status().json({ data })
│       └── book.routes.ts     # Router with validate() + writeLimiter on POST/PATCH
└── tests/
    ├── helpers/
    │   └── testApp.ts         # createApp({ db: openDb(':memory:'), rateLimit: { disabled: true } })
    ├── books.create.test.ts
    ├── books.list.test.ts     # ← contains the scripted red→green test
    ├── books.stats.test.ts
    ├── books.update.test.ts
    └── security.test.ts       # helmet headers, 415, 413, 429, 404 envelope, no stack leak
```

### 3.1 Dependencies

```bash
npm i express@5 zod better-sqlite3 helmet cors express-rate-limit pino pino-http dotenv
npm i -D typescript tsx vitest supertest @types/express @types/supertest @types/better-sqlite3 @types/cors @types/node
```

### 3.2 Scripts (`package.json`)

```json
{
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc -p tsconfig.json",
    "start": "node dist/index.js",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit",
    "audit": "npm audit --audit-level=high"
  }
}
```

### 3.3 Environment (`.env.example`)

```env
NODE_ENV=development
PORT=4000
LOG_LEVEL=info
DB_PATH=./data/books.db
CORS_ORIGIN=http://localhost:5173
TRUST_PROXY=false
RATE_LIMIT_WINDOW_MS=900000
RATE_LIMIT_MAX=100
WRITE_RATE_LIMIT_WINDOW_MS=60000
WRITE_RATE_LIMIT_MAX=20
RATE_LIMIT_DISABLED=false
JSON_BODY_LIMIT=10kb
```

`config/env.ts` parses this with Zod and **fails fast** on startup if invalid.

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

- DB-level `CHECK` constraints are defence in depth behind Zod.
- Pragmas: `journal_mode = WAL`, `foreign_keys = ON`.
- Repository maps `snake_case` columns → `camelCase` `Book`.
- Stats query: `SELECT status, COUNT(*) AS n FROM books GROUP BY status`, then fill missing statuses with `0` in the service so the shape is always complete.

Repository interface:

```ts
export interface BookRepository {
  insert(book: Book): Book;
  findAll(filter?: { status?: BookStatus }): Book[];
  findById(id: string): Book | undefined;
  updateStatus(id: string, status: BookStatus, updatedAt: string): Book | undefined;
  countByStatus(): Partial<Record<BookStatus, number>>;
}
```

All SQL uses `?` placeholders via prepared statements. **Never** interpolate values into SQL strings.

---

## 5. Request pipeline (order matters)

```
requestId
→ pino-http (logs method, url, status, duration, requestId; redacts nothing sensitive because none exists)
→ helmet()
→ cors(allowlist)
→ globalLimiter                      (all /api/*)
→ express.json({ limit: JSON_BODY_LIMIT, strict: true })
→ requireJson                        (415 on wrong content-type when body present)
→ /api/v1/health
→ /api/v1/books router
     GET  /            validate({ query: listQuerySchema })
     GET  /stats
     POST /            writeLimiter, validate({ body: createBookSchema })
     PATCH /:id        writeLimiter, validate({ params: idParamSchema, body: updateStatusSchema })
→ notFound (404)
→ errorHandler
```

Route ordering note: register `GET /stats` **before** `PATCH /:id`/any `/:id` route so `stats` is never treated as an id.

### 5.1 Error handler behaviour

| Incoming | Response |
|---|---|
| `HttpError` | its status + `{ error: { code, message, details? } }` |
| Zod error (from `validate`) | `400 VALIDATION_ERROR` with flattened `details` |
| `entity.too.large` (body-parser) | `413 PAYLOAD_TOO_LARGE` |
| `entity.parse.failed` (bad JSON) | `400 VALIDATION_ERROR`, message "Malformed JSON" |
| anything else | `500 INTERNAL_ERROR`, generic message; full error logged with requestId. **Never** send `err.stack` or `err.message` to the client |

---

## 6. Security — OWASP Top 10 (2021) mapping

| # | Risk | Mitigation in this service | Where |
|---|---|---|---|
| A01 | Broken Access Control | No auth in scope (single-user assignment) — documented. CORS allowlist, only `GET/POST/PATCH` exposed, no `DELETE`, no wildcard routes. `TRUST_PROXY` off by default so `req.ip` cannot be spoofed via `X-Forwarded-For`. | `app.ts`, `env.ts` |
| A02 | Cryptographic Failures | No secrets/PII stored. HSTS via helmet (effective when served over TLS). `.env` gitignored. TLS terminated at reverse proxy in prod. | `helmet`, `.gitignore` |
| A03 | Injection | All input validated with Zod (types, lengths, enum). Parameterized SQL only. `express.json({ strict: true })` rejects non-object JSON. Responses are JSON — no HTML templating, no reflection of raw input in error messages. | `book.schema.ts`, `book.repository.ts` |
| A04 | Insecure Design | Rate limiting (global + stricter write). Body size cap `10kb`. Server-generated UUIDs (client cannot choose ids). Enum allowlist for status. Fail-fast config validation. | `rateLimit.ts`, `app.ts` |
| A05 | Security Misconfiguration | `helmet()` (CSP, X-Content-Type-Options, frame-ancestors, referrer policy, HSTS). `x-powered-by` disabled. Stack traces never returned. Explicit CORS methods/headers. Unknown routes → JSON 404, not Express HTML. | `app.ts`, `errorHandler.ts` |
| A06 | Vulnerable & Outdated Components | `package-lock.json` committed. `npm audit --audit-level=high` script; run in CI. Pin major versions. Minimal dependency surface. | `package.json` |
| A07 | Identification & Auth Failures | N/A — no accounts. Documented as out of scope; extension point: auth middleware slot before `/api/v1/books` router. | this doc |
| A08 | Software & Data Integrity | Lockfile + `npm ci` in CI. No `eval`, no dynamic `require`. DB `CHECK` constraints enforce integrity independent of app code. | `migrate.ts` |
| A09 | Security Logging & Monitoring | `pino-http` structured logs with `requestId`, status, latency. Explicitly log at `warn` on `429` and on `400` validation failures (counts abuse attempts). `500`s logged at `error` with stack (server side only). | `logger.ts`, `errorHandler.ts` |
| A10 | SSRF | Service makes **no outbound HTTP requests**. No URL fields accepted. | by design |

Additional hardening:
- `express.json` `strict: true` + `type: 'application/json'`.
- Zod `.strict()` on body schemas → unknown fields rejected (mass-assignment protection).
- `title`/`author` trimmed; control characters stripped (`/[\u0000-\u001F\u007F]/g`).
- `Cache-Control: no-store` on all `/api` responses.

---

## 7. Rate limiting — implementation detail

```ts
// middleware/rateLimit.ts
import rateLimit from 'express-rate-limit';

export function makeLimiters(cfg: Config) {
  const passthrough = (_req, _res, next) => next();
  if (cfg.RATE_LIMIT_DISABLED) return { globalLimiter: passthrough, writeLimiter: passthrough };

  const handler = (req, res, _next, options) => {
    const retryAfter = Math.ceil(options.windowMs / 1000);
    req.log?.warn({ ip: req.ip, path: req.path }, 'rate limited');
    res.setHeader('Retry-After', String(retryAfter));
    res.status(429).json({ error: { code: 'RATE_LIMITED', message: `Too many requests, try again in ${retryAfter} seconds` } });
  };

  const globalLimiter = rateLimit({
    windowMs: cfg.RATE_LIMIT_WINDOW_MS, limit: cfg.RATE_LIMIT_MAX,
    standardHeaders: 'draft-7', legacyHeaders: false, handler,
  });
  const writeLimiter = rateLimit({
    windowMs: cfg.WRITE_RATE_LIMIT_WINDOW_MS, limit: cfg.WRITE_RATE_LIMIT_MAX,
    standardHeaders: 'draft-7', legacyHeaders: false, handler,
    skip: (req) => !['POST', 'PATCH'].includes(req.method),
  });
  return { globalLimiter, writeLimiter };
}
```

- Memory store is fine for one process. For multi-instance, swap in `rate-limit-redis` — interface unchanged.
- `app.set('trust proxy', cfg.TRUST_PROXY)` — set `true`/hop count only behind a known proxy, otherwise limits are trivially bypassed.
- Tests: default helper disables limiters; `security.test.ts` builds an app with `RATE_LIMIT_MAX=3` to assert the 4th request → `429` + `Retry-After`.

---

## 8. Testing plan

Test app: `createApp({ db: openDb(':memory:'), config: { ...testConfig, RATE_LIMIT_DISABLED: true } })`, fresh per test file (`beforeEach` re-migrates or reopens `:memory:`). Supertest hits the app in-process — no port.

| File | Cases |
|---|---|
| `books.create.test.ts` | 201 + full Book shape, defaults `status=to-read`, `author=''`; 400 missing title; 400 whitespace title; 400 title > 200; 400 invalid status; 400 unknown field; 400 malformed JSON; 415 wrong content-type |
| `books.list.test.ts` | 200 empty array; returns all sorted `createdAt DESC`; **filter by each status returns only matching**; 400 on invalid `status` query |
| `books.stats.test.ts` | all zeros when empty; correct counts + `total`; keys always present |
| `books.update.test.ts` | 200 updates status + bumps `updatedAt`; 404 unknown uuid; 404 malformed id; 400 invalid status; 400 missing status |
| `security.test.ts` | `x-powered-by` absent; `x-content-type-options: nosniff`; 404 envelope for unknown route; 413 on >10kb body; 429 after limit with `Retry-After` and `RateLimit-*` headers; 500 body has no `stack` |

### 8.1 Scripted red → green (for the on-screen requirement)

Do this **live**, in this order:

1. Implement `POST /books` and `GET /books` **without** reading `req.query.status` (list returns everything). Commit: `feat(books): create + list`.
2. Write the test in `books.list.test.ts`:
   ```ts
   it('GET /books?status=reading returns only reading books', async () => {
     await api.post('/api/v1/books').send({ title: 'A', status: 'reading' });
     await api.post('/api/v1/books').send({ title: 'B', status: 'done' });
     await api.post('/api/v1/books').send({ title: 'C', status: 'reading' });
     const res = await api.get('/api/v1/books?status=reading').expect(200);
     expect(res.body.data).toHaveLength(2);
     expect(res.body.data.every((b) => b.status === 'reading')).toBe(true);
   });
   ```
3. Run `npm test` → **RED** (`expected 3 to have length 2`). Commit: `test(books): add status filter test (failing)`.
4. Add `listQuerySchema` + `validate({ query })` + pass `filter` to `repo.findAll`.
5. Run `npm test` → **GREEN**. Commit: `feat(books): filter list by status`.

Backup red→green candidate if needed: the "400 invalid status on create" test before adding the enum to the Zod schema.

---

## 9. Build order (session checklist)

1. `npm init -y`, install deps, `tsconfig.json` (strict, `module: NodeNext`, `outDir: dist`), `vitest.config.ts`, `.env.example`, `.gitignore`.
2. `config/env.ts` (Zod), `lib/logger.ts`, `lib/httpError.ts`.
3. `db/connection.ts`, `db/migrate.ts`.
4. `modules/books/book.schema.ts` + `book.types.ts` (copy `BookStatus`/`Book` exactly from §2.2).
5. `book.repository.ts` (SQLite, prepared statements).
6. `middleware/*` (requestId, requireJson, validate, rateLimit, notFound, errorHandler).
7. `app.ts` (`createApp(deps)`), `index.ts` (bootstrap).
8. `book.service.ts`, `book.controller.ts`, `book.routes.ts` — create + list first (no filter).
9. `tests/helpers/testApp.ts`, `books.create.test.ts`, `books.list.test.ts` → run red→green script (§8.1).
10. `stats`, `PATCH /:id` + their tests.
11. `security.test.ts`; verify helmet headers with `curl -I`.
12. `npm run typecheck && npm test && npm audit`.
13. Smoke with curl (see §10), then hand off to frontend session.

---

## 10. Manual smoke (curl)

```bash
curl -s localhost:4000/api/v1/health
curl -s -X POST localhost:4000/api/v1/books -H 'Content-Type: application/json' -d '{"title":"Dune","author":"Frank Herbert"}'
curl -s 'localhost:4000/api/v1/books?status=to-read'
curl -s localhost:4000/api/v1/books/stats
curl -s -X PATCH localhost:4000/api/v1/books/<id> -H 'Content-Type: application/json' -d '{"status":"reading"}'
curl -s -X POST localhost:4000/api/v1/books -H 'Content-Type: application/json' -d '{"title":"","status":"nope"}'   # 400
curl -s -X POST localhost:4000/api/v1/books -d 'title=x'                                                           # 415
for i in $(seq 1 25); do curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:4000/api/v1/books -H 'Content-Type: application/json' -d '{"title":"x"}'; done | sort | uniq -c   # expect some 429
curl -sI localhost:4000/api/v1/health | grep -iE 'x-powered-by|content-security-policy|x-content-type-options|ratelimit'
```

---

## 11. Definition of done

- [ ] All endpoints in §2.4 return exactly the envelope in §2.3.
- [ ] Validation rules in §2.4 enforced; DB `CHECK` constraints present.
- [ ] `helmet`, CORS allowlist, body limit, `x-powered-by` off.
- [ ] Global + write rate limiters with standard headers and `Retry-After`.
- [ ] Structured logs with request id; 429/400 at `warn`, 500 at `error`.
- [ ] `npm test` green; red→green commit history for the filter test.
- [ ] `npm audit --audit-level=high` clean.
- [ ] `.env.example` complete; `README` snippet: install, run, test, env.
- [ ] Frontend session can run `npm run dev` here and hit every endpoint via Vite proxy with zero changes.
