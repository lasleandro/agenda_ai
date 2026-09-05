# Agenda platform image.
#
# One image, several roles (see scripts/deploy/entrypoint.sh, ROLE env var):
#   platform  (default) - supervised Next.js (public :$PORT) + FastAPI (loopback)
#   api                 - FastAPI only, public
#   webhook-processor / candidate-worker / escalation-worker /
#   scheduled-task-worker / email-worker - a single background worker
#   migrate             - run Alembic to head and exit
#
# Build from the repository root:
#   docker build -t agenda-platform .

# ---------------------------------------------------------------------------
# Stage 1 - build the Next.js standalone server
# ---------------------------------------------------------------------------
FROM node:20-bookworm-slim AS frontend-build

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /build/frontend

# Copy manifests first to leverage Docker layer cache
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY VERSION /build/VERSION
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 - runtime: Python + a single Node binary for the standalone server
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=1 \
    NEXT_TELEMETRY_DISABLED=1 \
    TZ=America/Sao_Paulo \
    PORT=8080 \
    INTERNAL_API_PORT=8005

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# node:20 and python:3.11-slim share the bookworm base, so the standalone
# server needs only the node binary (no npm) at runtime.
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node

WORKDIR /app

# Install Python dependencies from the unified root requirements first
COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Backend application, migrations, and deploy scripts
COPY backend/ ./backend/
COPY scripts/deploy/ ./scripts/deploy/

# Next.js standalone output -> /app/frontend (server.js at /app/frontend/server.js)
COPY --from=frontend-build /build/frontend/.next/standalone/ ./frontend/
COPY --from=frontend-build /build/frontend/.next/static/ ./frontend/.next/static/
COPY --from=frontend-build /build/frontend/public/ ./frontend/public/

# Create non-root user
RUN useradd -ms /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Healthcheck: /health for API roles, no-op for worker roles (see script)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["/bin/bash", "scripts/deploy/healthcheck.sh"]

ENTRYPOINT ["/bin/bash", "scripts/deploy/entrypoint.sh"]
