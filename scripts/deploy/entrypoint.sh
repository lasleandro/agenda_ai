#!/usr/bin/env bash
# Container entrypoint. One image, many roles, selected by $ROLE.
set -euo pipefail

: "${ROLE:=platform}"
: "${PORT:=8080}"
: "${INTERNAL_API_PORT:=8005}"
: "${ENVIRONMENT:=production}"

echo "Starting agenda role=${ROLE} (ENVIRONMENT=${ENVIRONMENT})"

# Optional DB readiness wait: set DB_WAIT_HOST (and DB_WAIT_PORT, default 5432).
if [[ -n "${DB_WAIT_HOST:-}" ]]; then
  echo "Waiting for database ${DB_WAIT_HOST}:${DB_WAIT_PORT:-5432} ..."
  for i in $(seq 1 30); do
    if timeout 2 bash -c "</dev/tcp/${DB_WAIT_HOST}/${DB_WAIT_PORT:-5432}" 2>/dev/null; then
      echo "Database is reachable"
      break
    fi
    echo "... retry ${i}"
    sleep 2
  done
fi

# The platform role is supervised from /app (Next.js standalone lives there);
# every other role runs a Python module from the backend package.
if [[ "${ROLE}" == "platform" ]]; then
  exec python scripts/deploy/supervisor.py
fi

cd backend

case "${ROLE}" in
  api)
    exec python -m uvicorn app.main:app \
      --host 0.0.0.0 --port "${PORT}" --workers "${API_WORKERS:-1}"
    ;;
  migrate)
    exec python -m alembic -c alembic.ini upgrade head
    ;;
  webhook-processor)
    exec python -m app.chat.webhook_processor_worker
    ;;
  candidate-worker)
    exec python -m app.chat.candidate_worker
    ;;
  escalation-worker)
    exec python -m app.chat.passive_escalation_worker
    ;;
  scheduled-task-worker)
    exec python -m app.chat.scheduled_task_worker
    ;;
  email-worker)
    exec python -m app.chat.email_delivery_worker
    ;;
  *)
    echo "Unknown ROLE: ${ROLE}" >&2
    exit 1
    ;;
esac
