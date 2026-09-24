# Books UI

Single-page React app to add books, filter them by status, change a book's status, and see counts per status.
Implements [`TECHNICAL_SPEC.md`](./TECHNICAL_SPEC.md); talks to the API described in `../server/TECHNICAL_SPEC.md` §2.

## Requirements

- Node ≥ 20 (tested with Node 26 / npm 11)
- The backend on `http://localhost:4000` for `npm run dev`. The tests do **not** need it; they use MSW.

## Quick start

```bash
npm ci
npm run dev          # http://localhost:5173 — /api/* is proxied to http://localhost:4000
```

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Vite dev server with the `/api` proxy |
| `npm run build` | Type-check (`tsc -b`) and build a production bundle to `dist/` (no source maps) |
| `npm run preview` | Serve `dist/` on :4173 with production security headers and the same `/api` proxy |
| `npm test` | Vitest + React Testing Library + MSW (in-memory contract mock) |
| `npm run lint` | ESLint (typed rules, react-hooks, jsx-a11y strict, bans on XSS sinks) |
| `npm run typecheck` | `tsc -b --noEmit` |
| `npm run audit` | `npm audit --audit-level=high` |

CI order: `npm ci && npm run lint && npm run typecheck && npm test && npm run build && npm run audit`.

## Configuration

| Var | Default | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Empty = same-origin `/api/v1` (dev proxy or a reverse proxy in prod). Otherwise the API's absolute origin, e.g. `https://api.example.com`. Production builds **fail** for a non-HTTPS origin other than localhost. The origin is added to CSP `connect-src` automatically, and it must be in the backend's `CORS_ORIGIN`. |

Everything prefixed `VITE_` ends up in the public bundle, so never put secrets there.

## Architecture

```
src/
  api/          contract types, Zod schemas, fetch wrapper (request()), endpoint functions
  features/books/  query keys, React Query hooks, UI components
  components/   FeedbackRegion (toasts, live regions), RateLimitNotice, ErrorBoundary
  hooks/        useRateLimit, useStatusFilterParam (?status= in the URL)
  lib/          tiny external stores (feedback, rate limit), queryClient, format, reportError
tests/          RTL tests + MSW handlers that implement the API contract in memory
```

Main behaviours:

- **One place for HTTP** (`api/client.ts`): 10 s timeout, `X-Request-Id` on every request, parses the error envelope into `ApiError`, turns 429 into `RateLimitError` and updates the global rate-limit store, and validates every success payload with Zod before anything renders it.
- **Retries**: queries retry network errors and 5xx at most twice. They never retry 4xx or 429. Mutations never retry automatically.
- **Status changes are optimistic**: the row and the stats update immediately. On failure, only the affected row is rolled back. Every write then refetches from the server.
- **Rate limiting**: `Retry-After` (seconds or HTTP date) blocks every mutating control and shows a countdown. Screen readers hear one announcement, not one per tick. When the block ends, "You can try again now." is announced.
- **Accessibility**: every control has a label, errors are linked with `aria-describedby`, the live regions are always mounted, the filter uses native radios (so arrow keys work), focus goes back to the status select after an update, colour is never the only signal, and reduced motion is respected.

## Security (OWASP Top 10 2021, client side)

| Area | Mitigation in this app |
|---|---|
| A03 XSS | React text rendering only. `dangerouslySetInnerHTML`, `innerHTML`, `insertAdjacentHTML`, `eval`, and `new Function` are banned by ESLint. CSP `<meta>` is injected at build time with `script-src 'self'` and no inline scripts. A test asserts that markup in titles renders as text. |
| A08 Integrity | All responses are validated with Zod, so malformed data becomes an error state and never renders (covered by a test). No CDN scripts. The lockfile is committed; use `npm ci`. |
| A04 Design | Client validation mirrors the server's rules. Submit is disabled while pending. `Retry-After` is honoured and there are no retry storms. |
| A05 Config | No source maps in `dist/`. `no-referrer`. The ErrorBoundary shows a generic message and never a stack trace. |
| A09 Logging | `reportError()` is the single hook for Sentry or similar. It logs status, method, path, and request id, never bodies. |
| A10 SSRF | Only fixed paths are used, plus an enum-validated `?status=` and an encoded id. `?status=` from the URL is validated too. |

### Hosting headers

`<meta>` CSP cannot set `frame-ancestors`. When you deploy `dist/` to a static host or CDN, send these as real headers. `npm run preview` already does:

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' <API origin>; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

## Deviations from the spec (and why)

- **Vite 8 / Vitest 5 / plugin-react 6 instead of Vite 5 / Vitest 2.** With Vite 5, `npm audit --audit-level=high` reports high and critical advisories (esbuild, vite, @vitest/mocker), which breaks the Definition of Done. The API and behaviour are unchanged.
- **Query keys are `['books','list',{status}]` instead of `['books',{status}]`.** Everything still sits under `['books']`, so a single invalidation covers lists and stats as the spec intends. The extra `'list'` segment lets optimistic updates target every cached list without a predicate.
- **CSP `frame-ancestors` is sent as a header, not a meta tag**, because browsers ignore it in `<meta>` (see above). In dev only, CSP also allows the React Fast Refresh inline preamble and the `ws:` connection used for HMR.
- **Retry policy**: the spec's example retried nothing that is an `ApiError`. This app still never retries 4xx or 429, but it does retry network errors and 5xx up to twice, which is what the spec's rationale asks for.
