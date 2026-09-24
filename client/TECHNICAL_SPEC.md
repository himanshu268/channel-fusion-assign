# Books UI — Frontend Technical Specification

> Scope: frontend only. The backend has its own spec at `server/TECHNICAL_SPEC.md`.
> Section 2 ("Integration Contract") is duplicated verbatim in both specs. If you change it here, change it there too.

---

## 0. Assignment (source of truth)

- **UI** — a single page to add a book, view the list, and change a book's status. Basic success/error feedback.
- **Data** — books have `title`, `author`, `status` (`to-read` / `reading` / `done`). List is filterable by status. One aggregation (count by status) is shown.
- **Validation** — `title` required; `status` must be one of the three values. Mirror server rules client-side, but the server is authoritative.
- **Non-functional** — OWASP Top 10 (2021) client-side mitigations; graceful handling of backend rate limiting (`429`).

---

## 1. Stack & decisions

| Concern | Choice | Why |
|---|---|---|
| Framework | React 18 + TypeScript (strict) | Auto-escaped rendering (A03), ubiquitous |
| Build | Vite 5 | Fast dev, built-in `/api` proxy → no CORS in dev |
| Server state | TanStack Query v5 | Loading/error/retry states, cache invalidation after mutations, no hand-rolled `useEffect` fetches |
| Validation | Zod | Same schema shape as backend; also used to **validate API responses** at runtime |
| HTTP | native `fetch` wrapped in `api/client.ts` | Zero deps; central place for timeout, envelope parsing, 429 handling |
| Styling | plain CSS (`styles.css`, CSS variables) | No framework needed for one page; swap for Tailwind if desired |
| Tests | Vitest + React Testing Library + MSW | Component tests against a mocked API that speaks the exact contract |
| Lint | ESLint + `eslint-plugin-react-hooks` + `eslint-plugin-jsx-a11y` | Catch hook misuse and a11y regressions |

**Explicit non-goals:** routing (single page), auth, offline support, deleting books, pagination.

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
client/
├── package.json
├── vite.config.ts             # /api proxy → http://localhost:4000, vitest config
├── tsconfig.json
├── index.html                 # CSP <meta>, no inline scripts
├── .env.example               # VITE_API_BASE_URL=
├── .gitignore
├── src/
│   ├── main.tsx               # QueryClientProvider, <App/>
│   ├── App.tsx                # page layout: StatsBar, AddBookForm, StatusFilter, BookList, FeedbackRegion
│   ├── styles.css
│   ├── api/
│   │   ├── types.ts           # Book, BookStatus, BookStats, ApiError — copy of §2.2/2.3
│   │   ├── schemas.ts         # Zod: bookSchema, bookStatsSchema, apiErrorSchema, createBookInput, BOOK_STATUSES
│   │   ├── client.ts          # request<T>(): base URL, JSON headers, timeout, envelope parse, ApiError, 429 → RateLimitError
│   │   └── books.ts           # createBook, listBooks(status?), updateBookStatus(id, status), getStats
│   ├── features/books/
│   │   ├── queryKeys.ts       # ['books', { status }], ['books','stats']
│   │   ├── useBooks.ts        # useBooksQuery(filter), useStatsQuery, useCreateBook, useUpdateStatus
│   │   ├── AddBookForm.tsx    # controlled form, client validation, disabled while pending / rate-limited
│   │   ├── StatusFilter.tsx   # All | to-read | reading | done (radio group / segmented)
│   │   ├── BookList.tsx       # loading / empty / error / list states
│   │   ├── BookRow.tsx        # title, author, <select> status → useUpdateStatus
│   │   └── StatsBar.tsx       # counts per status + total
│   ├── components/
│   │   ├── FeedbackRegion.tsx # aria-live region for success/error toasts
│   │   └── RateLimitNotice.tsx# countdown from Retry-After
│   ├── hooks/
│   │   └── useRateLimit.ts    # global "blocked until" state fed by client.ts on 429
│   └── lib/
│       ├── feedback.ts        # tiny pub/sub store for toasts (or Context)
│       └── format.ts          # status label map, date formatting
└── tests/
    ├── setup.ts               # RTL cleanup, MSW server lifecycle
    ├── mocks/
    │   ├── handlers.ts        # MSW handlers implementing §2.4 exactly (in-memory array)
    │   └── server.ts
    ├── AddBookForm.test.tsx
    ├── BookList.test.tsx
    ├── StatusFilter.test.tsx
    ├── StatusChange.test.tsx
    └── RateLimit.test.tsx
```

### 3.1 Dependencies

```bash
npm create vite@latest . -- --template react-ts
npm i @tanstack/react-query zod
npm i -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom msw eslint-plugin-jsx-a11y eslint-plugin-react-hooks
```

### 3.2 Scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "audit": "npm audit --audit-level=high"
  }
}
```

### 3.3 Vite config

```ts
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:4000', changeOrigin: true } },
  },
  test: { environment: 'jsdom', setupFiles: './tests/setup.ts', globals: true },
});
```

### 3.4 Environment

```env
# .env.example
VITE_API_BASE_URL=            # empty in dev → relative "/api/v1" via proxy. Prod: https://api.example.com
```

Only `VITE_*` vars reach the bundle. **Never** put secrets in frontend env — everything here is public.

---

## 4. API client design

```ts
// api/client.ts
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: { path: string; message: string }[]) { super(message); }
}
export class RateLimitError extends ApiError {
  constructor(public retryAfterSeconds: number, message: string) { super(429, 'RATE_LIMITED', message); }
}

const BASE = `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1`;

export async function request<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 10_000);
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
      signal: ctrl.signal,
    });
    const json = await res.json().catch(() => null);
    if (res.status === 429) {
      const retry = Number(res.headers.get('Retry-After') ?? 60);
      rateLimitStore.block(retry);                       // feeds useRateLimit()
      throw new RateLimitError(retry, json?.error?.message ?? 'Too many requests');
    }
    if (!res.ok) {
      const err = apiErrorSchema.safeParse(json);
      throw err.success
        ? new ApiError(res.status, err.data.error.code, err.data.error.message, err.data.error.details)
        : new ApiError(res.status, 'INTERNAL_ERROR', 'Something went wrong');
    }
    return schema.parse(json.data);                     // runtime-validate the response (A08)
  } finally { clearTimeout(t); }
}
```

`api/books.ts` is four one-liners over `request()` with the right schema (`bookSchema`, `z.array(bookSchema)`, `bookStatsSchema`).

Query behaviour (`useBooks.ts`):
- `useBooksQuery(status?)` key `['books', { status: status ?? 'all' }]`, `staleTime: 10s`.
- `useStatsQuery()` key `['books','stats']`.
- `useCreateBook` / `useUpdateStatus`: on success → `invalidateQueries({ queryKey: ['books'] })` (covers list + stats) and push success toast; on error → push error toast (validation `details` mapped to field errors in the form).
- `useUpdateStatus` does **optimistic update** of the row's `status` with rollback on error.
- Global `QueryClient` default: `retry: (count, err) => !(err instanceof ApiError) && count < 2` — never retry 4xx/429 automatically.

---

## 5. UI specification (single page)

```
┌──────────────────────────────────────────────────────────┐
│ Books                                    [StatsBar]       │
│   to-read 3 · reading 1 · done 2 · total 6                │
├──────────────────────────────────────────────────────────┤
│ Add a book                                                │
│ Title*  [__________________]   Author [________________]  │
│ Status  (● to-read ○ reading ○ done)          [ Add book ]│
│ ⓘ inline field errors under inputs                        │
├──────────────────────────────────────────────────────────┤
│ Filter: [All] [To read] [Reading] [Done]                  │
├──────────────────────────────────────────────────────────┤
│ Dune              Frank Herbert         [ to-read  ▼ ]    │
│ Neuromancer       William Gibson        [ reading  ▼ ]    │
│ …                                                         │
│ (empty state: "No books yet — add one above.")            │
├──────────────────────────────────────────────────────────┤
│ [aria-live] ✓ "Dune" added   /   ✗ Title is required      │
│ [RateLimitNotice] Too many requests — retry in 42s        │
└──────────────────────────────────────────────────────────┘
```

Behaviour:
- **AddBookForm**: `title` `required maxLength=200`, `author` `maxLength=200`, status radio default `to-read`. Client Zod check on submit → inline errors, no request. Submit button disabled while `isPending` or rate-limited (prevents double submit). On success: reset form, focus title, toast `“<title>” added`. On `400`: map `details[].path` → field error. Other errors → toast `error.message`.
- **StatusFilter**: local state `status | undefined`; drives `useBooksQuery`. Reflect in URL `?status=` via `history.replaceState` (nice-to-have).
- **BookList**: states — `isPending` skeleton (3 rows), `isError` inline error + Retry button (`refetch`), empty, list. Rows keyed by `id`.
- **BookRow**: `<select aria-label="Status for <title>">` with the three options; `onChange` → `useUpdateStatus`. Row shows subtle spinner while pending; select disabled during mutation. Toast on success `Moved “<title>” to Reading`.
- **StatsBar**: from `useStatsQuery`; shows `—` while loading; always renders all four keys.
- **FeedbackRegion**: `role="status" aria-live="polite"` for success, `role="alert"` for errors. Auto-dismiss success after 4s; errors stay until next action or dismiss click.
- **RateLimitNotice**: appears when `useRateLimit().blockedUntil > now`; live countdown; all mutating controls disabled while shown. Reads never blocked (global limit is generous), but a 429 on a read shows the notice too.

Accessibility baseline: every input has a `<label>`; errors linked via `aria-describedby`; visible focus rings; colour is never the only status indicator (label text always present); keyboard-only path works for add → filter → change status.

---

## 6. Security — OWASP Top 10 (2021), client-side responsibilities

| # | Risk | Frontend mitigation | Where |
|---|---|---|---|
| A01 | Broken Access Control | No auth in scope. Client never assumes success — every mutation refetches server truth. No client-side "admin" toggles. Only `GET/POST/PATCH` used, matching backend CORS allowlist. | `useBooks.ts` |
| A02 | Cryptographic Failures | Nothing sensitive stored: no `localStorage`/cookies for data. `VITE_*` env treated as public. Prod served over HTTPS; `VITE_API_BASE_URL` must be `https://`. | `.env.example` |
| A03 | Injection (XSS) | React JSX auto-escapes. **Zero** `dangerouslySetInnerHTML`. No `innerHTML`, `eval`, `new Function`. Titles/authors rendered as text nodes only. No user-controlled URLs/`href`. CSP meta tag: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' <API origin>; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`. Inputs trimmed + `maxLength`. | `index.html`, all components |
| A04 | Insecure Design | Client validation mirrors server (fail fast, fewer bad requests). Submit disabled while pending (no double-post). Honour `429`/`Retry-After` — no auto-retry storms. 10s fetch timeout. | `client.ts`, `AddBookForm.tsx` |
| A05 | Security Misconfiguration | CSP meta; `<meta name="referrer" content="no-referrer">`; no source maps shipped to prod (`build.sourcemap: false`); no debug flags in bundle; strict TS + ESLint. | `index.html`, `vite.config.ts` |
| A06 | Vulnerable Components | `package-lock.json` committed; `npm audit --audit-level=high` in CI; minimal deps (react, react-query, zod). | `package.json` |
| A07 | Identification & Auth Failures | N/A — documented. Extension point: `client.ts` header injection. | this doc |
| A08 | Software & Data Integrity | **All API responses validated with Zod before render** — malformed/unexpected data throws instead of rendering. No third-party CDN scripts (everything bundled). Lockfile + `npm ci`. | `client.ts`, `schemas.ts` |
| A09 | Logging & Monitoring | `console.error` with `X-Request-Id` from response on any non-2xx (correlates with backend logs). Hook for error reporter (Sentry etc.) left as a single function `reportError()`. | `client.ts` |
| A10 | SSRF | Frontend never builds request URLs from user input; only fixed paths + validated enum query. | `books.ts` |

Extra:
- `rel="noopener noreferrer"` on any external link (currently none).
- Do not log request bodies in production builds.
- Error messages shown to users come from `error.message` in the envelope (server guarantees they are safe/generic) — never render raw `Error.stack` or `JSON.stringify(err)`.

---

## 7. Testing plan (Vitest + RTL + MSW)

MSW handlers implement §2.4 faithfully against an in-memory array, including validation → `400` envelope, `404`, and a switchable `429` mode with `Retry-After`. This makes the frontend testable **without the backend running** and doubles as a contract check: if MSW handlers and `server/TECHNICAL_SPEC.md` §2 disagree, the contract has drifted.

| File | Cases |
|---|---|
| `AddBookForm.test.tsx` | submits valid book → row appears + success toast; empty title → inline error, **no request** (assert MSW not hit); server `400` details → mapped to field error; button disabled while pending |
| `BookList.test.tsx` | shows skeleton then rows; empty state; server `500` → error + Retry works |
| `StatusFilter.test.tsx` | click "Reading" → request has `?status=reading` and only matching rows render; "All" clears filter |
| `StatusChange.test.tsx` | change select → `PATCH /books/:id` sent with `{status}`, row updates optimistically, stats refetched; server `404` → rollback + error toast |
| `RateLimit.test.tsx` | MSW returns `429 Retry-After: 3` → notice visible, Add button disabled, countdown decrements (fake timers), re-enabled after |

Optional e2e (Playwright / `agent-browser`) against real backend: add → filter → change status → stats update. Not required for the assignment.

---

## 8. Build order (session checklist)

1. Scaffold Vite React-TS in `client/`, install deps, `vite.config.ts` with proxy + vitest, `tsconfig` strict, `.env.example`, `.gitignore`.
2. `index.html`: CSP + referrer meta, `lang="en"`, title.
3. `api/types.ts` + `api/schemas.ts` — copy §2.2/2.3 exactly. `BOOK_STATUSES = ['to-read','reading','done'] as const`.
4. `api/client.ts` (`request`, `ApiError`, `RateLimitError`, rate-limit store hook), `api/books.ts`.
5. `features/books/queryKeys.ts`, `useBooks.ts`.
6. `components/FeedbackRegion.tsx`, `lib/feedback.ts`.
7. `StatsBar`, `AddBookForm`, `StatusFilter`, `BookList`, `BookRow`, `RateLimitNotice`; compose in `App.tsx`; `styles.css`.
8. `tests/mocks/handlers.ts` + `server.ts` + `setup.ts`; write the five test files.
9. `npm run lint && npm run typecheck && npm test && npm run build`.
10. Integration run: start backend (`cd ../server && uv run python -m app`), start `npm run dev`, walk §9 checklist.

---

## 9. Integration checklist (with backend running on :4000)

- [ ] Page loads; StatsBar shows zeros; empty state visible.
- [ ] Add "Dune" → 201, row appears at top, stats `to-read 1 · total 1`, success toast.
- [ ] Submit empty title → inline error, Network tab shows **no** request.
- [ ] Devtools: `fetch('/api/v1/books',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'x',status:'bad'})})` → UI toast not triggered (direct call), but response is `400` envelope as per §2.3.
- [ ] Filter "Reading" → request `?status=reading`, list filtered.
- [ ] Change Dune → `reading` → row updates instantly, stats move `to-read 0 · reading 1`.
- [ ] Hammer Add 21× within a minute → `429`, RateLimitNotice with countdown, Add disabled, re-enabled after `Retry-After`.
- [ ] Stop backend → list shows error + Retry; start backend → Retry recovers.
- [ ] `curl -I localhost:5173` in `vite preview` / prod: CSP meta present in HTML; no source maps in `dist/`.

---

## 10. Definition of done

- [ ] Single page implements add / list / filter / change status / stats per §5.
- [ ] Client validation mirrors §2.4; server errors surfaced via envelope `message`/`details`.
- [ ] Success + error feedback via live regions; rate-limit notice honours `Retry-After`.
- [ ] No `dangerouslySetInnerHTML`, CSP meta present, responses Zod-validated.
- [ ] `npm run lint`, `typecheck`, `test`, `build`, `audit` all pass.
- [ ] `README` snippet: install, run (needs backend on :4000 or `VITE_API_BASE_URL`), test.
- [ ] Works against the backend from `server/TECHNICAL_SPEC.md` with **zero** code changes on either side.
