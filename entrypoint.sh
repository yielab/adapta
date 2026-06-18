#!/bin/sh
# Container entrypoint: run migrations, then start the API server.
# Any migration failure is fatal — the app must not start against a stale schema.
set -e

echo "[entrypoint] Running database migrations..."
alembic upgrade head
echo "[entrypoint] Migrations complete."

# Development convenience: seed a default admin on an EMPTY database so the
# console is usable immediately. Gated by ADAPTA_SEED_DEFAULT_ADMIN; a no-op if
# any organization already exists (never clobbers a real bootstrap).
python -m adapta.db.seed

if [ "${ADAPTA_RELOAD:-0}" = "1" ]; then
    echo "[entrypoint] Starting API server (reload mode)..."
    exec uvicorn adapta.api.app:app \
        --host "${ADAPTA_HOST:-0.0.0.0}" \
        --port "${ADAPTA_PORT:-8000}" \
        --reload
else
    echo "[entrypoint] Starting API server..."
    exec uvicorn adapta.api.app:app \
        --host "${ADAPTA_HOST:-0.0.0.0}" \
        --port "${ADAPTA_PORT:-8000}" \
        --workers "${ADAPTA_WORKERS:-1}"
fi
