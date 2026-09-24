import { type FormEvent, useId, useRef, useState } from 'react';

import { ApiError } from '../../api/client';
import { AUTHOR_MAX, BOOK_STATUSES, TITLE_MAX, createBookInputSchema } from '../../api/schemas';
import type { BookStatus } from '../../api/types';
import { useRateLimit } from '../../hooks/useRateLimit';
import { feedback } from '../../lib/feedback';
import { STATUS_LABELS } from '../../lib/format';

import { useCreateBook } from './useBooks';

type Field = 'title' | 'author' | 'status';
type FieldErrors = Partial<Record<Field, string>>;

const FIELDS: readonly Field[] = ['title', 'author', 'status'];
// Native maxLength counts UTF-16 units; a code point is at most 2, so this never blocks a valid
// value (e.g. emoji). The exact code-point limit is enforced by createBookInputSchema.
const INPUT_MAX_UNITS = (max: number) => max * 2;
const isField = (path: string): path is Field => (FIELDS as readonly string[]).includes(path);

export function AddBookForm() {
  const id = useId();
  const titleRef = useRef<HTMLInputElement>(null);
  const authorRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [status, setStatus] = useState<BookStatus>('to-read');
  const [errors, setErrors] = useState<FieldErrors>({});

  const createBook = useCreateBook();
  const { isLimited } = useRateLimit();
  const disabled = createBook.isPending || isLimited;

  function focusFirstError(fieldErrors: FieldErrors) {
    if (fieldErrors.title) titleRef.current?.focus();
    else if (fieldErrors.author) authorRef.current?.focus();
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;

    // Fail fast on the client (A04); the server re-validates and stays authoritative.
    const parsed = createBookInputSchema.safeParse({ title, author, status });
    if (!parsed.success) {
      const fieldErrors: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const path = String(issue.path[0] ?? '');
        if (isField(path)) fieldErrors[path] ??= issue.message;
      }
      setErrors(fieldErrors);
      focusFirstError(fieldErrors);
      return;
    }

    setErrors({});
    const { author: trimmedAuthor, ...rest } = parsed.data;
    createBook.mutate(trimmedAuthor ? { ...rest, author: trimmedAuthor } : rest, {
      onSuccess: () => {
        setTitle('');
        setAuthor('');
        setStatus('to-read');
        titleRef.current?.focus();
      },
      onError: (error) => {
        if (!(error instanceof ApiError) || error.code !== 'VALIDATION_ERROR' || !error.details?.length) return;
        const fieldErrors: FieldErrors = {};
        const unmapped: string[] = [];
        for (const detail of error.details) {
          if (isField(detail.path)) fieldErrors[detail.path] ??= detail.message;
          else unmapped.push(detail.message);
        }
        setErrors(fieldErrors);
        focusFirstError(fieldErrors);
        feedback.error(unmapped.length ? unmapped.join(' ') : 'Couldn’t add book — please fix the highlighted fields.');
      },
    });
  }

  const clearError = (field: Field) => setErrors((prev) => (prev[field] ? { ...prev, [field]: undefined } : prev));

  const titleErrorId = `${id}-title-error`;
  const authorErrorId = `${id}-author-error`;
  const statusErrorId = `${id}-status-error`;

  return (
    <section className="card" aria-labelledby={`${id}-heading`}>
      <h2 id={`${id}-heading`}>Add a book</h2>
      <form className="add-form" onSubmit={onSubmit} noValidate>
        <div className="field">
          <label htmlFor={`${id}-title`}>
            Title <span aria-hidden="true">*</span>
          </label>
          <input
            ref={titleRef}
            id={`${id}-title`}
            name="title"
            type="text"
            autoComplete="off"
            required
            maxLength={INPUT_MAX_UNITS(TITLE_MAX)}
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              clearError('title');
            }}
            aria-invalid={errors.title ? true : undefined}
            aria-describedby={errors.title ? titleErrorId : undefined}
          />
          {errors.title && (
            <p id={titleErrorId} className="field-error">
              {errors.title}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor={`${id}-author`}>Author</label>
          <input
            ref={authorRef}
            id={`${id}-author`}
            name="author"
            type="text"
            autoComplete="off"
            maxLength={INPUT_MAX_UNITS(AUTHOR_MAX)}
            value={author}
            onChange={(e) => {
              setAuthor(e.target.value);
              clearError('author');
            }}
            aria-invalid={errors.author ? true : undefined}
            aria-describedby={errors.author ? authorErrorId : undefined}
          />
          {errors.author && (
            <p id={authorErrorId} className="field-error">
              {errors.author}
            </p>
          )}
        </div>

        <fieldset className="field status-radios" aria-describedby={errors.status ? statusErrorId : undefined}>
          <legend>Status</legend>
          <div className="radio-row">
            {BOOK_STATUSES.map((value) => (
              <label key={value} className="radio">
                <input
                  type="radio"
                  name="status"
                  value={value}
                  checked={status === value}
                  onChange={() => {
                    setStatus(value);
                    clearError('status');
                  }}
                />
                {STATUS_LABELS[value]}
              </label>
            ))}
          </div>
          {errors.status && (
            <p id={statusErrorId} className="field-error">
              {errors.status}
            </p>
          )}
        </fieldset>

        <div className="form-actions">
          <button type="submit" className="button primary" disabled={disabled} aria-busy={createBook.isPending || undefined}>
            {createBook.isPending ? 'Adding…' : 'Add book'}
          </button>
        </div>
      </form>
    </section>
  );
}
