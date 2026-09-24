export interface ErrorContext {
  requestId?: string | null;
  status?: number;
  method?: string;
  path?: string;
  [key: string]: unknown;
}

/**
 * Single hook point for error monitoring (OWASP A09). Wire Sentry/Datadog/etc. here.
 * Never pass request bodies or user input in `context` — only correlation metadata.
 */
export function reportError(error: unknown, context: ErrorContext = {}): void {
  if (import.meta.env.MODE === 'test') return;
  const message = error instanceof Error ? error.message : String(error);
  console.error('[books-ui]', message, context);
}
