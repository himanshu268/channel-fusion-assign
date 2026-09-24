import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';

import { feedback } from '../src/lib/feedback';
import { rateLimitStore } from '../src/lib/rateLimitStore';

import { mockApi } from './mocks/handlers';
import { server } from './mocks/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

afterEach(() => {
  cleanup();
  server.resetHandlers();
  mockApi.reset();
  feedback.reset();
  rateLimitStore.reset();
  window.history.replaceState(null, '', '/');
  vi.useRealTimers();
});

afterAll(() => server.close());
