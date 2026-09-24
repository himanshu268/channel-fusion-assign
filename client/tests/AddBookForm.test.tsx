import { screen, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';

import { mockApi } from './mocks/handlers';
import { server } from './mocks/server';
import { formStatusRadio, renderWithClient, stat, titles } from './utils';

describe('AddBookForm', () => {
  it('submits a valid book → row appears, stats update, success toast, form resets', async () => {
    const { user } = renderWithClient();
    await screen.findByText('No books yet — add one above.');

    const title = screen.getByLabelText(/title/i);
    await user.type(title, '  Dune  ');
    await user.type(screen.getByLabelText('Author'), 'Frank Herbert');
    await user.click(screen.getByRole('button', { name: 'Add book' }));

    expect(await screen.findByText('“Dune” added')).toBeInTheDocument();
    await waitFor(() => expect(titles()).toEqual(['Dune']));
    expect(screen.getByText('Frank Herbert')).toBeInTheDocument();
    await waitFor(() => expect(stat('to-read')).toHaveTextContent('1'));
    expect(stat('total')).toHaveTextContent('1');

    const [post] = mockApi.requestsTo('POST', '/api/v1/books');
    expect(post?.body).toEqual({ title: 'Dune', author: 'Frank Herbert', status: 'to-read' });
    expect(title).toHaveValue('');
    expect(title).toHaveFocus();
  });

  it('sends the chosen status', async () => {
    const { user } = renderWithClient();
    await user.type(screen.getByLabelText(/title/i), 'Neuromancer');
    await user.click(formStatusRadio('Reading'));
    await user.click(screen.getByRole('button', { name: 'Add book' }));

    await screen.findByText('“Neuromancer” added');
    expect(mockApi.all()[0]).toMatchObject({ title: 'Neuromancer', status: 'reading', author: '' });
    expect(mockApi.requestsTo('POST', '/api/v1/books')[0]?.body).not.toHaveProperty('author');
  });

  it('empty / whitespace title → inline error and NO request', async () => {
    const { user } = renderWithClient();
    await screen.findByText('No books yet — add one above.');

    const title = screen.getByLabelText(/title/i);
    await user.type(title, '   ');
    await user.click(screen.getByRole('button', { name: 'Add book' }));

    const error = await screen.findByText('Title is required');
    expect(title).toHaveAttribute('aria-invalid', 'true');
    expect(title).toHaveAttribute('aria-describedby', error.id);
    expect(title).toHaveFocus();
    expect(mockApi.requestsTo('POST', '/api/v1/books')).toHaveLength(0);

    await user.type(title, 'x');
    expect(screen.queryByText('Title is required')).not.toBeInTheDocument();
  });

  it('caps inputs at 200 code points (native maxLength leaves room for 2-unit emoji)', async () => {
    const { user } = renderWithClient();
    const title = screen.getByLabelText(/title/i);
    expect(title).toHaveAttribute('maxLength', '400');
    expect(screen.getByLabelText('Author')).toHaveAttribute('maxLength', '400');

    await user.click(title);
    await user.paste('x'.repeat(201));
    await user.click(screen.getByRole('button', { name: 'Add book' }));
    expect(await screen.findByText('Title must be at most 200 characters')).toBeInTheDocument();
    expect(mockApi.requestsTo('POST', '/api/v1/books')).toHaveLength(0);
  });

  it('maps server 400 details to field errors', async () => {
    const { user, queryClient } = renderWithClient();
    // Server is authoritative: it may reject input the client considered valid.
    server.use(
      http.post('*/api/v1/books', () =>
        HttpResponse.json(
          { error: { code: 'VALIDATION_ERROR', message: 'Invalid request body', details: [{ path: 'author', message: 'Author is not allowed' }] } },
          { status: 400 },
        ),
      ),
    );

    await user.type(screen.getByLabelText(/title/i), 'Dune');
    await user.type(screen.getByLabelText('Author'), 'Someone');
    await user.click(screen.getByRole('button', { name: 'Add book' }));

    expect(await screen.findByText('Author is not allowed')).toBeInTheDocument();
    expect(screen.getByLabelText('Author')).toHaveAttribute('aria-invalid', 'true');
    // Field errors get one summary toast (not the raw per-field messages); form keeps user input.
    expect(screen.getByText('Couldn’t add book — please fix the highlighted fields.')).toBeInTheDocument();
    expect(screen.getByLabelText(/title/i)).toHaveValue('Dune');
    expect(queryClient.isMutating()).toBe(0);
  });

  it('shows a toast for non-validation server errors', async () => {
    const { user } = renderWithClient();
    mockApi.failNext(500, 'INTERNAL_ERROR', 'Internal server error', { method: 'POST' });
    await user.type(screen.getByLabelText(/title/i), 'Dune');
    await user.click(screen.getByRole('button', { name: 'Add book' }));

    const alert = await screen.findByText('Internal server error');
    expect(alert.closest('[role="alert"]')).not.toBeNull();
  });

  it('disables submit while the request is pending (no double submit)', async () => {
    mockApi.latency(150);
    const { user } = renderWithClient();
    await user.type(screen.getByLabelText(/title/i), 'Dune');
    await user.click(screen.getByRole('button', { name: 'Add book' }));

    const button = screen.getByRole('button', { name: 'Adding…' });
    expect(button).toBeDisabled();
    await user.click(button);

    await screen.findByText('“Dune” added');
    // Stays pending until the list/stats refetch completes, then re-enables.
    expect(await screen.findByRole('button', { name: 'Add book' })).toBeEnabled();
    expect(mockApi.requestsTo('POST', '/api/v1/books')).toHaveLength(1);
  });
});
