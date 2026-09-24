import { FeedbackRegion } from './components/FeedbackRegion';
import { RateLimitNotice } from './components/RateLimitNotice';
import { AddBookForm } from './features/books/AddBookForm';
import { BookList } from './features/books/BookList';
import { StatsBar } from './features/books/StatsBar';
import { StatusFilter } from './features/books/StatusFilter';
import { useStatusFilterParam } from './hooks/useStatusFilterParam';

export function App() {
  const [status, setStatus] = useStatusFilterParam();

  return (
    <>
      <header className="page-header">
        <div className="page header-inner">
          <h1>Books</h1>
          <StatsBar />
        </div>
      </header>
      <main className="page">
        <RateLimitNotice />
        <AddBookForm />
        <StatusFilter value={status} onChange={setStatus} />
        <BookList status={status} />
      </main>
      <FeedbackRegion />
    </>
  );
}
