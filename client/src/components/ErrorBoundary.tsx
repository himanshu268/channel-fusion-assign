import { Component, type ErrorInfo, type ReactNode } from 'react';

import { reportError } from '../lib/reportError';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/** Last line of defence for render crashes: generic message, never the stack (OWASP A05/A09). */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    reportError(error, { componentStack: info.componentStack ?? undefined });
  }

  override render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <main className="page">
        <div className="card inline-error" role="alert">
          <p>Something went wrong while showing this page.</p>
          <button type="button" className="button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      </main>
    );
  }
}
