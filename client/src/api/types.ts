// Mirror of the Integration Contract (TECHNICAL_SPEC.md §2.2 / §2.3).
// Keep in sync with server/TECHNICAL_SPEC.md — `schemas.ts` asserts these match at compile time.

export type BookStatus = 'to-read' | 'reading' | 'done';

export interface Book {
  id: string; // UUID v4
  title: string; // 1..200 chars, trimmed
  author: string; // 0..200 chars, trimmed; '' when not given
  status: BookStatus; // default 'to-read'
  createdAt: string; // ISO 8601 UTC
  updatedAt: string; // ISO 8601 UTC
}

export interface BookStats {
  'to-read': number;
  reading: number;
  done: number;
  total: number;
}

export type ApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'NOT_FOUND'
  | 'UNSUPPORTED_MEDIA_TYPE'
  | 'PAYLOAD_TOO_LARGE'
  | 'RATE_LIMITED'
  | 'INTERNAL_ERROR';

/** Client-only codes for failures that never reached / never came back from the server. */
export type ClientErrorCode = 'NETWORK_ERROR' | 'TIMEOUT' | 'INVALID_RESPONSE';

export interface ApiErrorDetail {
  path: string;
  message: string;
}

export interface ApiErrorBody {
  error: {
    code: ApiErrorCode;
    message: string;
    details?: ApiErrorDetail[];
  };
}

export interface CreateBookInput {
  title: string;
  author?: string;
  status?: BookStatus;
}

export interface UpdateBookStatusInput {
  status: BookStatus;
}
