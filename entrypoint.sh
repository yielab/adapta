#!/bin/sh
# Container entrypoint: run migrations, then start the API server.
# Any migration failure is fatal — the app must not start against a stale schema.
set -e

echo "[entrypoint] Running database migrations..."
alembic upgrade head
echo "[entrypoint] Migrations complete."

if [ "${BRAIN_RELOAD:-0}" = "1" ]; then
    echo "[entrypoint] Starting API server (reload mode)..."
    exec uvicorn brain.api.app:app \
        --host "${BRAIN_HOST:-0.0.0.0}" \
        --port "${BRAIN_PORT:-8000}" \
        --reload
else
    echo "[entrypoint] Starting API server..."
    exec uvicorn brain.api.app:app \
        --host "${BRAIN_HOST:-0.0.0.0}" \
        --port "${BRAIN_PORT:-8000}" \
        --workers "${BRAIN_WORKERS:-1}"
fi
