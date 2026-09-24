import { screen, waitFor } from '@testing-library/react';

import { mockApi } from './mocks/handlers';
import { filterRadio, renderWithClient, titles } from './utils';

const seed = () =>
  mockApi.seed([
    { title: 'Dune', status: 'to-read' },
    { title: 'Neuromancer', status: 'reading' },
    { title: 'Snow Crash', status: 'reading' },
    { title: 'Foundation', status: 'done' },
  ]);

describe('StatusFilter', () => {
  it('"Reading" sends ?status=reading and renders only matching rows; "All" clears it', async () => {
    seed();
    const { user } = renderWithClient();
    await waitFor(() => expect(titles()).toHaveLength(4));
    expect(filterRadio('All')).toBeChecked();

    await user.click(filterRadio('Reading'));
    await waitFor(() => expect(titles()).toEqual(['Snow Crash', 'Neuromancer']));
    const listCalls = mockApi.requestsTo('GET', '/api/v1/books');
    expect(listCalls.at(-1)?.url.searchParams.get('status')).toBe('reading');
    expect(window.location.search).toBe('?status=reading');

    await user.click(filterRadio('All'));
    await waitFor(() => expect(titles()).toHaveLength(4));
    expect(window.location.search).toBe('');
  });

  it('shows a filter-specific empty state', async () => {
    mockApi.seed([{ title: 'Dune' }]);
    const { user } = renderWithClient();
    await waitFor(() => expect(titles()).toEqual(['Dune']));

    await user.click(filterRadio('Done'));
    expect(await screen.findByText('No books with status “Done”.')).toBeInTheDocument();
  });

  it('restores a valid filter from the URL and ignores invalid ones', async () => {
    seed();
    window.history.replaceState(null, '', '/?status=done');
    const { unmount } = renderWithClient();
    await waitFor(() => expect(titles()).toEqual(['Foundation']));
    expect(filterRadio('Done')).toBeChecked();
    unmount();

    window.history.replaceState(null, '', '/?status=<script>');
    renderWithClient();
    await waitFor(() => expect(titles()).toHaveLength(4));
    expect(filterRadio('All')).toBeChecked();
    expect(mockApi.requestsTo('GET', '/api/v1/books').at(-1)?.url.search).toBe('');
  });

  it('is keyboard operable (arrow keys move the selection)', async () => {
    seed();
    const { user } = renderWithClient();
    await waitFor(() => expect(titles()).toHaveLength(4));

    filterRadio('All').focus();
    await user.keyboard('{ArrowRight}');
    expect(filterRadio('To read')).toBeChecked();
    await waitFor(() => expect(titles()).toEqual(['Dune']));
  });
});
