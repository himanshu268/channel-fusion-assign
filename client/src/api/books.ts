import { request } from './client';
import { bookListSchema, bookSchema, bookStatsSchema } from './schemas';
import type { Book, BookStats, BookStatus, CreateBookInput } from './types';

// Only fixed paths + validated enum values / encoded ids are ever used (OWASP A10).

export const createBook = (input: CreateBookInput, signal?: AbortSignal): Promise<Book> =>
  request('/books', bookSchema, { method: 'POST', json: input, signal });

export const listBooks = (status?: BookStatus, signal?: AbortSignal): Promise<Book[]> =>
  request(status ? `/books?${new URLSearchParams({ status }).toString()}` : '/books', bookListSchema, { signal });

export const updateBookStatus = (id: string, status: BookStatus, signal?: AbortSignal): Promise<Book> =>
  request(`/books/${encodeURIComponent(id)}`, bookSchema, { method: 'PATCH', json: { status }, signal });

export const getStats = (signal?: AbortSignal): Promise<BookStats> => request('/books/stats', bookStatsSchema, { signal });
