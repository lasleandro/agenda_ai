#!/usr/bin/env bash
# Container HEALTHCHECK. API-bearing roles must answer /health; background
# workers have no socket, so their liveness is the process being up (and,
# in production, their own progress signals / orchestrator probes).
set -euo pipefail

case "${ROLE:-platform}" in
  platform|api)
    exec curl -fsS "http://127.0.0.1:${INTERNAL_API_PORT:-8005}/health"
    ;;
  *)
    exit 0
    ;;
esac
