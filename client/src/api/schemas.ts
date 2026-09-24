import { z } from 'zod';

import type { ApiErrorDetail, Book, BookStats, BookStatus, CreateBookInput } from './types';

export const BOOK_STATUSES = ['to-read', 'reading', 'done'] as const satisfies readonly BookStatus[];
export const TITLE_MAX = 200;
export const AUTHOR_MAX = 200;

const STATUS_MESSAGE = `Status must be one of: ${BOOK_STATUSES.join(', ')}`;

/** Server limits count Unicode code points (Python `len`), not UTF-16 units — emoji count as 1. */
const codePointLength = (value: string): number => [...value].length;
const withinCodePoints = (max: number) => (value: string) => codePointLength(value) <= max;

export const bookStatusSchema = z.enum(BOOK_STATUSES, { errorMap: () => ({ message: STATUS_MESSAGE }) });

// ---- Response schemas (OWASP A08: never render unvalidated data) ----
// Objects are intentionally non-strict: unknown extra fields from a newer server are stripped, not fatal.

const isoDate = z.string().datetime({ offset: true });

export const bookSchema = z.object({
  id: z.string().uuid(),
  title: z.string().min(1).refine(withinCodePoints(TITLE_MAX)),
  author: z.string().refine(withinCodePoints(AUTHOR_MAX)),
  status: bookStatusSchema,
  createdAt: isoDate,
  updatedAt: isoDate,
});

export const bookListSchema = z.array(bookSchema);

const count = z.number().int().nonnegative();
export const bookStatsSchema = z.object({
  'to-read': count,
  reading: count,
  done: count,
  total: count,
});

export const apiErrorDetailSchema = z.object({ path: z.string(), message: z.string() });

export const apiErrorSchema = z.object({
  error: z.object({
    // Unknown future codes are tolerated; the UI only relies on `message`.
    code: z.string(),
    message: z.string(),
    details: z.array(apiErrorDetailSchema).optional(),
  }),
});

// ---- Request schemas (mirror server validation; server stays authoritative) ----

export const createBookInputSchema = z
  .object({
    title: z
      .string({ required_error: 'Title is required' })
      .trim()
      .min(1, 'Title is required')
      .refine(withinCodePoints(TITLE_MAX), `Title must be at most ${TITLE_MAX} characters`),
    author: z
      .string()
      .trim()
      .refine(withinCodePoints(AUTHOR_MAX), `Author must be at most ${AUTHOR_MAX} characters`)
      .optional(),
    status: bookStatusSchema.optional(),
  })
  .strict();

export const updateBookStatusInputSchema = z.object({ status: bookStatusSchema }).strict();

// ---- Compile-time drift guard: schemas ⇔ hand-written contract types ----
type Equals<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
type Assert<T extends true> = T;
export type _ContractChecks = [
  Assert<Equals<z.infer<typeof bookSchema>, Book>>,
  Assert<Equals<z.infer<typeof bookStatsSchema>, BookStats>>,
  Assert<Equals<z.infer<typeof apiErrorDetailSchema>, ApiErrorDetail>>,
  Assert<Equals<z.output<typeof createBookInputSchema>, CreateBookInput>>,
];
