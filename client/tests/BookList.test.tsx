import { screen, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';

import { mockApi } from './mocks/handlers';
import { server } from './mocks/server';
import { renderWithClient, titles } from './utils';

describe('BookList', () => {
  it('shows a skeleton, then rows newest-first', async () => {
    mockApi.seed([
      { title: 'Dune', author: 'Frank Herbert' },
      { title: 'Neuromancer', author: 'William Gibson', status: 'reading' },
    ]);
    mockApi.latency(50);
    renderWithClient();

    expect(screen.getAllByTestId('skeleton-row')).toHaveLength(3);
    expect(screen.getByText('Loading books…')).toBeInTheDocument();

    await waitFor(() => expect(titles()).toEqual(['Neuromancer', 'Dune']));
    expect(screen.queryByTestId('skeleton-row')).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Status for Neuromancer' })).toHaveValue('reading');
  });

  it('renders "Unknown author" when author is empty', async () => {
    mockApi.seed([{ title: 'Anonymous' }]);
    renderWithClient();
    expect(await screen.findByText('Unknown author')).toBeInTheDocument();
  });

  it('shows the empty state', async () => {
    renderWithClient();
    expect(await screen.findByText('No books yet — add one above.')).toBeInTheDocument();
  });

  it('server 500 → inline error, Retry recovers', async () => {
    mockApi.seed([{ title: 'Dune' }]);
    mockApi.failNext(500, 'INTERNAL_ERROR', 'Internal server error', { method: 'GET', path: '/api/v1/books' });
    const { user } = renderWithClient();

    const retry = await screen.findByRole('button', { name: 'Retry' });
    expect(screen.getByText(/Couldn’t load books\. Internal server error/)).toBeInTheDocument();
    expect(titles()).toEqual([]);

    await user.click(retry);
    await waitFor(() => expect(titles()).toEqual(['Dune']));
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('never renders data that fails response validation (A08)', async () => {
    server.use(http.get('*/api/v1/books', () => HttpResponse.json({ data: [{ id: 'nope', title: '<img src=x onerror=alert(1)>' }] })));
    renderWithClient();

    expect(await screen.findByText(/Received an unexpected response from the server/)).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });

  it('renders user content as text, never HTML (A03)', async () => {
    mockApi.seed([{ title: '<img src=x onerror=alert(1)>', author: '<b>bold</b>' }]);
    renderWithClient();
    expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(screen.getByText('<b>bold</b>')).toBeInTheDocument();
    expect(document.querySelector('img, b')).toBeNull();
  });
});

describe('BookList retry', () => {
  it('Retry also refreshes the stats', async () => {
    mockApi.seed([{ title: 'Dune' }]);
    server.use(
      http.get('*/api/v1/books', () => new HttpResponse(null, { status: 503 }), { once: true }),
      http.get('*/api/v1/books/stats', () => new HttpResponse(null, { status: 503 }), { once: true }),
    );
    const { user } = renderWithClient();

    expect(await screen.findByText(/The server is unavailable right now/)).toBeInTheDocument();
    expect(screen.getByTestId('stat-total')).toHaveTextContent('—');

    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(titles()).toEqual(['Dune']));
    await waitFor(() => expect(screen.getByTestId('stat-total')).toHaveTextContent('1'));
  });
});
