import { act, screen, waitFor, within } from '@testing-library/react';

import { feedback } from '../src/lib/feedback';

import { mockApi } from './mocks/handlers';
import { renderWithClient, titles } from './utils';

const errorToasts = () => within(document.querySelector('.toasts ul[role="alert"]') as HTMLElement).queryAllByRole('listitem');

describe('API feedback toasts', () => {
  it('toasts when adding a book is rate limited', async () => {
    mockApi.rateLimit(5);
    const { user } = renderWithClient();
    await screen.findByText('No books yet — add one above.');

    await user.type(screen.getByLabelText(/title/i), 'Dune');
    await user.click(screen.getByRole('button', { name: 'Add book' }));

    await waitFor(() => expect(errorToasts()).toHaveLength(1));
    expect(errorToasts()[0]).toHaveTextContent('Too many requests, try again in 5 seconds');
  });

  it('toasts when a status change is rate limited', async () => {
    mockApi.seed([{ title: 'Dune' }]);
    const { user } = renderWithClient();
    await waitFor(() => expect(titles()).toEqual(['Dune']));

    mockApi.rateLimit(5);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Status for Dune' }), 'done');
    await waitFor(() => expect(errorToasts()[0]).toHaveTextContent('Too many requests'));
  });

  it('toasts a server 400 that has no field details', async () => {
    const { user } = renderWithClient();
    await screen.findByText('No books yet — add one above.');

    mockApi.failNext(400, 'VALIDATION_ERROR', 'Invalid request body', { method: 'POST' });
    await user.type(screen.getByLabelText(/title/i), 'Dune');
    await user.click(screen.getByRole('button', { name: 'Add book' }));

    await waitFor(() => expect(errorToasts()).toHaveLength(1));
  });

  it('toasts when stats fail to load', async () => {
    mockApi.failNext(500, 'INTERNAL_ERROR', 'Internal server error', { method: 'GET', path: '/api/v1/books/stats' });
    renderWithClient();
    await waitFor(() => expect(errorToasts()[0]).toHaveTextContent('Couldn’t load book stats. Internal server error'));
  });

  it('does not stack identical toasts', () => {
    renderWithClient();
    act(() => {
      feedback.error('Boom');
      feedback.error('Boom');
    });
    expect(errorToasts()).toHaveLength(1);
  });
});

describe('Unicode length limits (server counts code points)', () => {
  it('renders a book whose title is 200 emoji (400 UTF-16 units)', async () => {
    const title = '📚'.repeat(200);
    mockApi.seed([{ title }]);
    renderWithClient();
    await waitFor(() => expect(titles()).toEqual([title]));
  });

  it('lets the user add a 150-emoji title', async () => {
    const { user } = renderWithClient();
    await screen.findByText('No books yet — add one above.');
    const title = '📚'.repeat(150);
    await user.click(screen.getByLabelText(/title/i));
    await user.paste(title);
    expect(screen.getByLabelText(/title/i)).toHaveValue(title);
    await user.click(screen.getByRole('button', { name: 'Add book' }));
    await waitFor(() => expect(titles()).toEqual([title]));
  });
});
