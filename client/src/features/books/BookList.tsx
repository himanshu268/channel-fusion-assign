import { useQueryClient } from '@tanstack/react-query';
import { useId } from 'react';

import { STATUS_LABELS } from '../../lib/format';

import { BookRow } from './BookRow';
import { bookKeys, type StatusFilterValue } from './queryKeys';
import { useBooksQuery } from './useBooks';

interface BookListProps {
  status: StatusFilterValue;
}

const SKELETON_ROWS = 3;

export function BookList({ status }: BookListProps) {
  const headingId = useId();
  const queryClient = useQueryClient();
  const { data: books, isPending, isError, error, isFetching, isPlaceholderData } = useBooksQuery(status);
  // Retry everything on the page (list + stats) — if one failed, the other likely did too.
  const retry = () => void queryClient.refetchQueries({ queryKey: bookKeys.all, type: 'active' });

  const heading = (
    <h2 id={headingId} className="visually-hidden">
      {status ? `${STATUS_LABELS[status]} books` : 'All books'}
    </h2>
  );

  if (isPending) {
    return (
      <section className="card list-card" aria-labelledby={headingId} aria-busy="true">
        {heading}
        <p className="visually-hidden" role="status">
          Loading books…
        </p>
        <ul className="book-list" aria-hidden="true">
          {Array.from({ length: SKELETON_ROWS }, (_, i) => (
            <li key={i} className="book-row skeleton" data-testid="skeleton-row">
              <span className="skeleton-bar wide" />
              <span className="skeleton-bar" />
            </li>
          ))}
        </ul>
      </section>
    );
  }

  const retryButton = (
    <button type="button" className="button" onClick={retry} disabled={isFetching}>
      {isFetching ? 'Retrying…' : 'Retry'}
    </button>
  );

  if (isError && !books) {
    return (
      <section className="card list-card" aria-labelledby={headingId}>
        {heading}
        <div className="inline-error" role="alert">
          <p>Couldn’t load books. {error.message}</p>
          {retryButton}
        </div>
      </section>
    );
  }

  return (
    <section className="card list-card" aria-labelledby={headingId} aria-busy={isFetching || undefined}>
      {heading}
      {isError && (
        <div className="inline-error" role="alert">
          <p>Showing saved results — refreshing failed. {error.message}</p>
          {retryButton}
        </div>
      )}
      {books.length === 0 ? (
        <p className="empty-state">
          {/* Placeholder data belongs to the previous filter — don't claim this one is empty yet. */}
          {isPlaceholderData
            ? 'Loading books…'
            : status
              ? `No books with status “${STATUS_LABELS[status]}”.`
              : 'No books yet — add one above.'}
        </p>
      ) : (
        <ul className="book-list" data-stale={isPlaceholderData || undefined}>
          {books.map((book) => (
            <BookRow key={book.id} book={book} />
          ))}
        </ul>
      )}
    </section>
  );
}
