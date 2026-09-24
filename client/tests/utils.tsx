import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';

import { App } from '../src/App';
import { createQueryClient } from '../src/lib/queryClient';

export function renderWithClient(ui: ReactElement = <App />, { fakeTimers = false } = {}) {
  const queryClient = createQueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: Infinity } },
  });
  const user = userEvent.setup(fakeTimers ? { advanceTimers: (ms) => vi.advanceTimersByTime(ms) } : {});
  const result = render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
  return { ...result, user, queryClient };
}

/** Rendered book titles, in order. */
export function titles(): string[] {
  const list = document.querySelector('.book-list:not([aria-hidden])');
  if (!list) return [];
  return Array.from(list.querySelectorAll('.book-title')).map((el) => el.textContent ?? '');
}

export const stat = (key: 'to-read' | 'reading' | 'done' | 'total') => screen.getByTestId(`stat-${key}`);

/** Radios exist in both the form ("Status") and the filter ("Filter by status"); scope by fieldset. */
export const filterRadio = (name: string) => within(screen.getByRole('group', { name: 'Filter by status' })).getByRole('radio', { name });
export const formStatusRadio = (name: string) => within(screen.getByRole('group', { name: 'Status' })).getByRole('radio', { name });
