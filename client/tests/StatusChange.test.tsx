import { screen, waitFor } from '@testing-library/react';

import { mockApi } from './mocks/handlers';
import { renderWithClient, stat, titles } from './utils';

describe('Changing a book status', () => {
  it('sends PATCH {status}, updates the row optimistically, then refetches stats', async () => {
    const [dune] = mockApi.seed([{ title: 'Dune' }]);
    mockApi.latency(80);
    const { user } = renderWithClient();
    await waitFor(() => expect(titles()).toEqual(['Dune']));
    await waitFor(() => expect(stat('to-read')).toHaveTextContent('1'));

    const select = screen.getByRole('combobox', { name: 'Status for Dune' });
    await user.selectOptions(select, 'reading');

    // Optimistic: row + stats reflect the change before the server answers.
    expect(select).toHaveValue('reading');
    expect(select).toBeDisabled();
    expect(stat('reading')).toHaveTextContent('1');
    expect(stat('to-read')).toHaveTextContent('0');

    expect(await screen.findByText('Moved “Dune” to Reading')).toBeInTheDocument();
    await waitFor(() => expect(select).toBeEnabled());

    const [patch] = mockApi.requestsTo('PATCH', `/api/v1/books/${dune!.id}`);
    expect(patch?.body).toEqual({ status: 'reading' });
    expect(mockApi.all()[0]?.status).toBe('reading');
    // Stats were refetched from the server after the mutation settled.
    await waitFor(() => expect(mockApi.requestsTo('GET', '/api/v1/books/stats').length).toBeGreaterThanOrEqual(2));
    expect(stat('reading')).toHaveTextContent('1');
  });

  it('server 404 → rolls back the row and shows an error toast', async () => {
    mockApi.seed([{ title: 'Dune' }]);
    const { user } = renderWithClient();
    await waitFor(() => expect(titles()).toEqual(['Dune']));

    mockApi.failNext(404, 'NOT_FOUND', 'Book not found', { method: 'PATCH' });
    const select = screen.getByRole('combobox', { name: 'Status for Dune' });
    await user.selectOptions(select, 'done');

    const toast = await screen.findByText('Book not found');
    expect(toast.closest('[role="alert"]')).not.toBeNull();
    await waitFor(() => expect(select).toHaveValue('to-read'));
    expect(stat('done')).toHaveTextContent('0');
  });

  it('keeps focus on the select for keyboard users', async () => {
    mockApi.seed([{ title: 'Dune' }]);
    const { user } = renderWithClient();
    await waitFor(() => expect(titles()).toEqual(['Dune']));

    const select = screen.getByRole('combobox', { name: 'Status for Dune' });
    select.focus();
    await user.selectOptions(select, 'done');
    await screen.findByText('Moved “Dune” to Done');
    await waitFor(() => expect(select).toHaveFocus());
  });
});
