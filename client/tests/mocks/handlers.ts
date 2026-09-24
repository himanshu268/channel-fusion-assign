/**
 * In-memory implementation of the Integration Contract (TECHNICAL_SPEC.md §2.4).
 * Written independently of src/api/schemas.ts on purpose: if these handlers and the
 * server spec disagree with the client, the contract has drifted.
 */
import { http, HttpResponse, delay, type DefaultBodyType, type StrictRequest } from 'msw';

type Status = 'to-read' | 'reading' | 'done';
const STATUSES: readonly Status[] = ['to-read', 'reading', 'done'];
const STATUS_MSG = 'Status must be one of: to-read, reading, done';

export interface MockBook {
  id: string;
  title: string;
  author: string;
  status: Status;
  createdAt: string;
  updatedAt: string;
}

interface Detail {
  path: string;
  message: string;
}

// ---- mutable test state ----
let books: MockBook[] = [];
let clock = Date.parse('2026-09-24T10:00:00.000Z');
let rateLimit: { retryAfter: number; methods: string[] } | null = null;
interface Match {
  method?: string;
  path?: string;
}
let failNext: { status: number; code: string; message: string; match: Match } | null = null;
let latencyMs = 0;
export const requests: { method: string; url: URL; body: unknown }[] = [];

const tick = () => new Date((clock += 1000)).toISOString();
const isStatus = (v: unknown): v is Status => typeof v === 'string' && (STATUSES as readonly string[]).includes(v);
const uuid = () => crypto.randomUUID();

export const mockApi = {
  reset() {
    books = [];
    rateLimit = null;
    failNext = null;
    latencyMs = 0;
    requests.length = 0;
    clock = Date.parse('2026-09-24T10:00:00.000Z');
  },
  seed(items: { title: string; author?: string; status?: Status }[]) {
    // Seed oldest → newest so list order (createdAt DESC) is the reverse of input order.
    for (const item of items) {
      const now = tick();
      books.push({ id: uuid(), title: item.title, author: item.author ?? '', status: item.status ?? 'to-read', createdAt: now, updatedAt: now });
    }
    return [...books];
  },
  all: () => [...books],
  /** Answer every matching request with 429 until cleared. Default: writes only. */
  rateLimit(retryAfter: number, methods: string[] = ['POST', 'PATCH']) {
    rateLimit = { retryAfter, methods };
  },
  clearRateLimit() {
    rateLimit = null;
  },
  /** Fail the next request matching `match` (method and/or exact pathname) with an error envelope. */
  failNext(status: number, code = 'INTERNAL_ERROR', message = 'Internal server error', match: Match = {}) {
    failNext = { status, code, message, match };
  },
  latency(ms: number) {
    latencyMs = ms;
  },
  requestsTo(method: string, pathname: string) {
    return requests.filter((r) => r.method === method && r.url.pathname === pathname);
  },
};

// ---- envelope helpers ----
const ok = (data: unknown, status = 200) =>
  HttpResponse.json({ data }, { status, headers: { 'X-Request-Id': 'mock-req-id', 'RateLimit-Limit': '100', 'RateLimit-Remaining': '99' } });

const fail = (status: number, code: string, message: string, details?: Detail[], headers: Record<string, string> = {}) =>
  HttpResponse.json({ error: { code, message, ...(details ? { details } : {}) } }, { status, headers: { 'X-Request-Id': 'mock-req-id', ...headers } });

async function preflight(request: StrictRequest<DefaultBodyType>): Promise<Response | { body: unknown }> {
  const url = new URL(request.url);
  let body: unknown = undefined;
  if (request.method === 'POST' || request.method === 'PATCH') {
    const type = request.headers.get('Content-Type') ?? '';
    if (!type.includes('application/json')) return fail(415, 'UNSUPPORTED_MEDIA_TYPE', 'Content-Type must be application/json');
    try {
      body = await request.json();
    } catch {
      return fail(400, 'VALIDATION_ERROR', 'Invalid JSON body', [{ path: '', message: 'Malformed JSON' }]);
    }
  }
  requests.push({ method: request.method, url, body });

  if (latencyMs) await delay(latencyMs);

  if (rateLimit && rateLimit.methods.includes(request.method)) {
    const s = rateLimit.retryAfter;
    return fail(429, 'RATE_LIMITED', `Too many requests, try again in ${s} seconds`, undefined, {
      'Retry-After': String(s),
      'RateLimit-Limit': '20',
      'RateLimit-Remaining': '0',
      'RateLimit-Reset': String(s),
    });
  }
  if (
    failNext &&
    (!failNext.match.method || failNext.match.method === request.method) &&
    (!failNext.match.path || failNext.match.path === url.pathname)
  ) {
    const f = failNext;
    failNext = null;
    return fail(f.status, f.code, f.message);
  }
  return { body };
}

function validateCreate(body: unknown): Detail[] | { title: string; author: string; status: Status } {
  const details: Detail[] = [];
  if (typeof body !== 'object' || body === null || Array.isArray(body)) return [{ path: '', message: 'Body must be an object' }];
  const b = body as Record<string, unknown>;
  for (const key of Object.keys(b)) if (!['title', 'author', 'status'].includes(key)) details.push({ path: key, message: `Unrecognized key: ${key}` });

  const title = typeof b.title === 'string' ? b.title.trim() : '';
  if (!title) details.push({ path: 'title', message: 'Title is required' });
  else if ([...title].length > 200) details.push({ path: 'title', message: 'Title must be at most 200 characters' });

  let author = '';
  if (b.author !== undefined) {
    if (typeof b.author !== 'string') details.push({ path: 'author', message: 'Author must be a string' });
    else if ([...b.author.trim()].length > 200) details.push({ path: 'author', message: 'Author must be at most 200 characters' });
    else author = b.author.trim();
  }

  if (b.status !== undefined && !isStatus(b.status)) details.push({ path: 'status', message: STATUS_MSG });
  const status = isStatus(b.status) ? b.status : 'to-read';

  return details.length ? details : { title, author, status };
}

const API = '*/api/v1';

export const handlers = [
  http.get(`${API}/health`, () => ok({ status: 'ok' })),

  http.get(`${API}/books/stats`, async ({ request }) => {
    const pre = await preflight(request);
    if (pre instanceof Response) return pre;
    const count = (s: Status) => books.filter((b) => b.status === s).length;
    return ok({ 'to-read': count('to-read'), reading: count('reading'), done: count('done'), total: books.length });
  }),

  http.get(`${API}/books`, async ({ request }) => {
    const pre = await preflight(request);
    if (pre instanceof Response) return pre;
    const status = new URL(request.url).searchParams.get('status');
    if (status !== null && !isStatus(status)) return fail(400, 'VALIDATION_ERROR', 'Invalid query', [{ path: 'status', message: STATUS_MSG }]);
    const list = books.filter((b) => !status || b.status === status).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    return ok(list);
  }),

  http.post(`${API}/books`, async ({ request }) => {
    const pre = await preflight(request);
    if (pre instanceof Response) return pre;
    const result = validateCreate(pre.body);
    if (Array.isArray(result)) return fail(400, 'VALIDATION_ERROR', 'Invalid request body', result);
    const now = tick();
    const book: MockBook = { id: uuid(), ...result, createdAt: now, updatedAt: now };
    books.push(book);
    return ok(book, 201);
  }),

  http.patch(`${API}/books/:id`, async ({ request, params }) => {
    const pre = await preflight(request);
    if (pre instanceof Response) return pre;
    const body = pre.body as Record<string, unknown> | null;
    const details: Detail[] = [];
    if (!body || typeof body !== 'object') details.push({ path: '', message: 'Body must be an object' });
    else {
      for (const key of Object.keys(body)) if (key !== 'status') details.push({ path: key, message: `Unrecognized key: ${key}` });
      if (!isStatus(body.status)) details.push({ path: 'status', message: STATUS_MSG });
    }
    if (details.length) return fail(400, 'VALIDATION_ERROR', 'Invalid request body', details);

    const book = books.find((b) => b.id === params.id);
    if (!book) return fail(404, 'NOT_FOUND', 'Book not found');
    book.status = body!.status as Status;
    book.updatedAt = tick();
    return ok({ ...book });
  }),
];
