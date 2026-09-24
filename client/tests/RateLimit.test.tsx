import { act, screen, waitFor } from '@testing-library/react';

import { mockApi } from './mocks/handlers';
import { renderWithClient, titles } from './utils';

describe('Rate limiting (429 + Retry-After)', () => {
  it('shows a countdown, disables mutating controls, and re-enables after Retry-After', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockApi.seed([{ title: 'Dune' }]);
    mockApi.rateLimit(3);
    const { user } = renderWithClient(undefined, { fakeTimers: true });
    await waitFor(() => expect(titles()).toEqual(['Dune']));

    await user.type(screen.getByLabelText(/title/i), 'Neuromancer');
    await user.click(screen.getByRole('button', { name: 'Add book' }));

    const notice = await screen.findByTestId('rate-limit-notice');
    expect(notice).toHaveTextContent('retry in 3s');
    expect(screen.getByText(/paused for 3 seconds/)).toHaveAttribute('role', 'alert');
    expect(screen.getByRole('button', { name: 'Add book' })).toBeDisabled();
    expect(screen.getByRole('combobox', { name: 'Status for Dune' })).toBeDisabled();
    // Reads stay available; the typed title is kept for the retry.
    expect(screen.getByLabelText(/title/i)).toHaveValue('Neuromancer');

    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(notice).toHaveTextContent('retry in 2s');

    mockApi.clearRateLimit();
    await act(() => vi.advanceTimersByTimeAsync(2100));
    expect(screen.queryByTestId('rate-limit-notice')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add book' })).toBeEnabled();
    expect(screen.getByText('You can try again now.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Add book' }));
    expect(await screen.findByText('“Neuromancer” added')).toBeInTheDocument();
    // Exactly one blocked attempt + one successful one: no automatic retry storm.
    expect(mockApi.requestsTo('POST', '/api/v1/books')).toHaveLength(2);
  });

  it('a 429 on a read also shows the notice', async () => {
    mockApi.rateLimit(5, ['GET']);
    renderWithClient();
    expect(await screen.findByTestId('rate-limit-notice')).toHaveTextContent('retry in 5s');
  });

  it('rolls back an optimistic status change that was rate limited', async () => {
    mockApi.seed([{ title: 'Dune' }]);
    const { user } = renderWithClient();
    await waitFor(() => expect(titles()).toEqual(['Dune']));

    mockApi.rateLimit(10);
    const select = screen.getByRole('combobox', { name: 'Status for Dune' });
    await user.selectOptions(select, 'done');

    await screen.findByTestId('rate-limit-notice');
    expect(select).toHaveValue('to-read');
    expect(screen.getByTestId('stat-done')).toHaveTextContent('0');
  });
});
