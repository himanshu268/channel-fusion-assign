import { memo, useId, useRef } from 'react';

import { BOOK_STATUSES, bookStatusSchema } from '../../api/schemas';
import type { Book } from '../../api/types';
import { useRateLimit } from '../../hooks/useRateLimit';
import { STATUS_LABELS, formatDate } from '../../lib/format';

import { useUpdateStatus } from './useBooks';

interface BookRowProps {
  book: Book;
}

export const BookRow = memo(function BookRow({ book }: BookRowProps) {
  const id = useId();
  const selectRef = useRef<HTMLSelectElement>(null);
  const updateStatus = useUpdateStatus();
  const { isLimited } = useRateLimit();

  function onChange(raw: string) {
    const parsed = bookStatusSchema.safeParse(raw);
    if (!parsed.success || parsed.data === book.status) return;

    // Disabling a focused <select> drops focus to <body>; restore it for keyboard users.
    const hadFocus = document.activeElement === selectRef.current;
    updateStatus.mutate(
      { book, status: parsed.data },
      {
        onSettled: () => {
          if (hadFocus) requestAnimationFrame(() => selectRef.current?.focus());
        },
      },
    );
  }

  return (
    <li className="book-row" aria-busy={updateStatus.isPending || undefined}>
      <div className="book-main">
        <span className="book-title" id={`${id}-title`}>
          {book.title}
        </span>
        <span className={book.author ? 'book-author' : 'book-author muted'}>{book.author || 'Unknown author'}</span>
      </div>
      <time className="book-date muted" dateTime={book.createdAt}>
        Added {formatDate(book.createdAt)}
      </time>
      <div className="book-status">
        <span className={`status-dot status-${book.status}`} aria-hidden="true" />
        <select
          ref={selectRef}
          aria-label={`Status for ${book.title}`}
          value={book.status}
          disabled={updateStatus.isPending || isLimited}
          onChange={(e) => onChange(e.target.value)}
        >
          {BOOK_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>
        <span className="spinner" aria-hidden="true" data-visible={updateStatus.isPending || undefined} />
      </div>
    </li>
  );
});
