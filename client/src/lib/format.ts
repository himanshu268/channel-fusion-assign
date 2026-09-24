import type { BookStatus } from '../api/types';

export const STATUS_LABELS: Record<BookStatus, string> = {
  'to-read': 'To read',
  reading: 'Reading',
  done: 'Done',
};

const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });

export function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : dateFormatter.format(date);
}
