# syntax=docker/dockerfile:1.7
# Single image: React UI (nginx) + Books API (uvicorn) in one container.
#   runtime (default) → nginx :8080 serves the UI and proxies /api → uvicorn 127.0.0.1:4000
#   api-test / ui-test → lint, typecheck and test suites

# ---------- UI ----------
FROM node:22-alpine AS ui-deps
WORKDIR /ui
COPY client/package.json client/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY client/ ./

FROM ui-deps AS ui-test
CMD ["sh", "-c", "npm run lint && npm run typecheck && npm test"]

FROM ui-deps AS ui-build
# Empty → same-origin "/api/v1", which nginx proxies to the API.
ENV VITE_API_BASE_URL=
RUN npm run build

# ---------- API ----------
FROM python:3.12-slim AS api-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
COPY server/pyproject.toml server/uv.lock ./

FROM api-base AS api-deps
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

FROM api-base AS api-test
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project
COPY server/app ./app
COPY server/tests ./tests
ENV PATH="/opt/venv/bin:$PATH" APP_ENV=test DB_PATH=:memory:
CMD ["sh", "-c", "ruff check . && mypy && pytest"]

# ---------- runtime ----------
FROM python:3.12-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled /etc/nginx/conf.d/* \
    && groupadd --system app && useradd --system --gid app --no-create-home app \
    && mkdir -p /data /tmp/nginx \
    && chown -R app:app /data /tmp/nginx /var/lib/nginx /var/log/nginx
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    PORT=4000 \
    DB_PATH=/data/books.db \
    CORS_ORIGIN=http://localhost:8080 \
    TRUST_PROXY=true
WORKDIR /app
COPY --from=api-deps /opt/venv /opt/venv
COPY server/app ./app
COPY --from=ui-build /ui/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 docker/start.sh /usr/local/bin/start.sh
USER app
VOLUME ["/data"]
EXPOSE 8080
# Goes through nginx → API, so it checks both processes.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health',timeout=2)" || exit 1
CMD ["start.sh"]
