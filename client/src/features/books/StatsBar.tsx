import type { BookStats } from '../../api/types';

import { useStatsQuery } from './useBooks';

const ITEMS: { key: keyof BookStats; label: string }[] = [
  { key: 'to-read', label: 'To read' },
  { key: 'reading', label: 'Reading' },
  { key: 'done', label: 'Done' },
  { key: 'total', label: 'Total' },
];

export function StatsBar() {
  const { data } = useStatsQuery();
  return (
    <dl className="stats" aria-label="Books by status">
      {ITEMS.map(({ key, label }) => (
        <div key={key} className={`stat stat-${key}`}>
          <dt>{label}</dt>
          <dd data-testid={`stat-${key}`}>{data ? data[key] : '—'}</dd>
        </div>
      ))}
    </dl>
  );
}
