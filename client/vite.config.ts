import react from '@vitejs/plugin-react';
import { loadEnv, type Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

/**
 * Resolve the API origin that the CSP `connect-src` must allow.
 * Empty VITE_API_BASE_URL → same-origin (dev proxy / reverse proxy in prod).
 * Production builds refuse plain-HTTP API origins (OWASP A02), except localhost.
 */
function resolveApiOrigin(raw: string | undefined, isProdBuild: boolean): string | null {
  const value = raw?.trim();
  if (!value) return null;

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`VITE_API_BASE_URL is not a valid absolute URL: "${value}"`);
  }
  const isLocal = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
  if (isProdBuild && url.protocol !== 'https:' && !isLocal) {
    throw new Error(`VITE_API_BASE_URL must use https:// in production builds (got "${url.origin}")`);
  }
  return url.origin;
}

function buildCsp(apiOrigin: string | null, dev: boolean): string {
  const connect = ["'self'", apiOrigin, dev ? 'ws:' : null].filter(Boolean).join(' ');
  return [
    "default-src 'self'",
    // Dev only: @vitejs/plugin-react injects an inline Fast Refresh preamble.
    `script-src 'self'${dev ? " 'unsafe-inline'" : ''}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src ${connect}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ');
}

/**
 * Injects the CSP <meta> into index.html. `frame-ancestors` is ignored by browsers
 * when delivered via <meta>, so it is only sent as a real header (see `preview.headers`
 * and the README's hosting notes).
 */
function cspPlugin(apiOrigin: string | null): Plugin {
  let dev = false;
  return {
    name: 'books-ui:csp',
    configResolved(config) {
      dev = config.command === 'serve';
    },
    transformIndexHtml(html) {
      const meta = `<meta http-equiv="Content-Security-Policy" content="${buildCsp(apiOrigin, dev)}" />`;
      // Right after <meta charset>, before any resource the policy governs.
      const out = html.replace(/(<meta charset="[^"]+"\s*\/?>)/i, `$1\n    ${meta}`);
      if (out === html) throw new Error('index.html must contain <meta charset> for CSP injection');
      return out;
    },
  };
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const apiOrigin = resolveApiOrigin(env.VITE_API_BASE_URL, command === 'build' && mode === 'production');
  const csp = buildCsp(apiOrigin, false);

  return {
    plugins: [react(), cspPlugin(apiOrigin)],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { '/api': { target: 'http://localhost:4000', changeOrigin: true } },
    },
    preview: {
      port: 4173,
      headers: {
        'Content-Security-Policy': `${csp}; frame-ancestors 'none'`,
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Referrer-Policy': 'no-referrer',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
      },
      proxy: { '/api': { target: 'http://localhost:4000', changeOrigin: true } },
    },
    build: {
      sourcemap: false,
      target: 'es2022',
    },
    test: {
      environment: 'jsdom',
      setupFiles: './tests/setup.ts',
      globals: true,
      include: ['tests/**/*.test.{ts,tsx}'],
      restoreMocks: true,
    },
  };
});
