import type { z } from 'zod';

import { rateLimitStore } from '../lib/rateLimitStore';
import { reportError } from '../lib/reportError';

import { apiErrorSchema } from './schemas';
import type { ApiErrorCode, ApiErrorDetail, ClientErrorCode } from './types';

export const REQUEST_TIMEOUT_MS = 10_000;
const DEFAULT_RETRY_AFTER_SECONDS = 60;
const GATEWAY_STATUSES = new Set([502, 503, 504]);

export class ApiError extends Error {
  override name = 'ApiError';

  constructor(
    /** HTTP status; 0 when the request never got a response. */
    public readonly status: number,
    public readonly code: ApiErrorCode | ClientErrorCode | (string & {}),
    message: string,
    public readonly details?: ApiErrorDetail[],
    public readonly requestId?: string | null,
  ) {
    super(message);
  }
}

export class RateLimitError extends ApiError {
  override name = 'RateLimitError';

  constructor(
    public readonly retryAfterSeconds: number,
    message: string,
    requestId?: string | null,
  ) {
    super(429, 'RATE_LIMITED', message, undefined, requestId);
  }
}

const BASE = `${(import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')}/api/v1`;

function buildUrl(path: string): string {
  // Paths are fixed strings from api/books.ts — never user-provided (OWASP A10).
  return new URL(`${BASE}${path}`, window.location.origin).toString();
}

function newRequestId(): string {
  // randomUUID needs a secure context; fall back for plain-http LAN testing.
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Retry-After may be delta-seconds or an HTTP-date (RFC 9110 §10.2.3). */
export function parseRetryAfter(headers: Headers): number {
  const raw = headers.get('Retry-After') ?? headers.get('RateLimit-Reset');
  if (raw) {
    const seconds = Number(raw);
    if (Number.isFinite(seconds) && seconds >= 0) return Math.max(1, Math.ceil(seconds));
    const date = Date.parse(raw);
    if (!Number.isNaN(date)) return Math.max(1, Math.ceil((date - Date.now()) / 1000));
  }
  return DEFAULT_RETRY_AFTER_SECONDS;
}

async function readJson(res: Response): Promise<unknown> {
  if (res.status === 204) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  /** JSON-serialisable body; sets Content-Type automatically. */
  json?: unknown;
}

/**
 * Single choke point for every API call:
 * timeout, envelope parsing, typed errors, 429 → global rate-limit state,
 * and runtime validation of the success payload (OWASP A08).
 */
export async function request<T>(path: string, schema: z.ZodType<T, z.ZodTypeDef, unknown>, options: RequestOptions = {}): Promise<T> {
  const { json, signal: externalSignal, headers, ...init } = options;
  const method = (init.method ?? 'GET').toUpperCase();
  const requestId = newRequestId();

  const controller = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener('abort', onExternalAbort, { once: true });
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path), {
      ...init,
      method,
      credentials: 'omit', // contract: no credentials
      headers: {
        Accept: 'application/json',
        'X-Request-Id': requestId,
        ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : undefined,
      signal: controller.signal,
    });
  } catch (cause) {
    // Caller-initiated aborts (e.g. React Query cancelling a stale query) propagate untouched.
    if (externalSignal?.aborted) throw cause;
    const error = timedOut
      ? new ApiError(0, 'TIMEOUT', 'The server took too long to respond. Please try again.', undefined, requestId)
      : new ApiError(0, 'NETWORK_ERROR', 'Could not reach the server. Check your connection and try again.', undefined, requestId);
    reportError(error, { requestId, method, path });
    throw error;
  } finally {
    clearTimeout(timeout);
    externalSignal?.removeEventListener('abort', onExternalAbort);
  }

  const serverRequestId = res.headers.get('X-Request-Id') ?? requestId;
  const body = await readJson(res);

  if (res.status === 429) {
    const retryAfter = parseRetryAfter(res.headers);
    rateLimitStore.block(retryAfter);
    const parsed = apiErrorSchema.safeParse(body);
    const message = parsed.success ? parsed.data.error.message : `Too many requests, try again in ${retryAfter} seconds`;
    const error = new RateLimitError(retryAfter, message, serverRequestId);
    reportError(error, { requestId: serverRequestId, status: 429, method, path });
    throw error;
  }

  if (!res.ok) {
    const parsed = apiErrorSchema.safeParse(body);
    const error = parsed.success
      ? new ApiError(res.status, parsed.data.error.code, parsed.data.error.message, parsed.data.error.details, serverRequestId)
      : new ApiError(
          res.status,
          'INTERNAL_ERROR',
          GATEWAY_STATUSES.has(res.status)
            ? 'The server is unavailable right now. Please try again shortly.'
            : 'Something went wrong. Please try again.',
          undefined,
          serverRequestId,
        );
    reportError(error, { requestId: serverRequestId, status: res.status, method, path });
    throw error;
  }

  const data = (body as { data?: unknown } | null)?.data;
  const result = schema.safeParse(data);
  if (!result.success) {
    const error = new ApiError(res.status, 'INVALID_RESPONSE', 'Received an unexpected response from the server.', undefined, serverRequestId);
    reportError(error, { requestId: serverRequestId, status: res.status, method, path, issues: result.error.issues.length });
    throw error;
  }
  return result.data;
}

/** React Query retry policy: never auto-retry client errors or 429 (no retry storms, OWASP A04). */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  if (error instanceof ApiError && error.code === 'INVALID_RESPONSE') return false;
  return failureCount < 2;
}
