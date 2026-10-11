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
    # Watch only the package: git worktrees under .claude/worktrees/ sit inside
    # the bind-mounted checkout, and a reload there kills live gates in flight.
    uvicorn adapta.api.app:app \
        --host "${ADAPTA_HOST:-0.0.0.0}" \
        --port "${ADAPTA_PORT:-8000}" \
        --reload --reload-dir /app/adapta &
    UVICORN_PID=$!
    trap 'kill -TERM "$UVICORN_PID" 2>/dev/null; wait "$UVICORN_PID"; exit 0' TERM INT

    # Watchdog (F1.6). The --reload supervisor does NOT respawn a server child that dies
    # (the kernel OOM-killer, kill -9): it idles as PID 1 and the API stays dead while the
    # container looks up. So PID 1 probes /health and, when the server stops answering,
    # exits non-zero; compose `restart: unless-stopped` then brings the container back.
    # Armed after the first successful probe (or ADAPTA_WATCHDOG_ARM_SECONDS, so a server
    # that never comes up is recycled too). A hot reload takes seconds, far below the ~30 s
    # of consecutive failures (6 x 5 s) needed to trip it.
    PROBE_URL="http://127.0.0.1:${ADAPTA_PORT:-8000}/health"
    ARM_DEADLINE=$(( $(date +%s) + ${ADAPTA_WATCHDOG_ARM_SECONDS:-300} ))
    armed=0
    fails=0
    while kill -0 "$UVICORN_PID" 2>/dev/null; do
        sleep 5 &
        wait $!
        if curl -fs --max-time 5 "$PROBE_URL" >/dev/null 2>&1; then
            armed=1
            fails=0
        else
            if [ "$(date +%s)" -ge "$ARM_DEADLINE" ]; then armed=1; fi
            if [ "$armed" = "1" ]; then fails=$((fails + 1)); fi
        fi
        if [ "$fails" -ge "${ADAPTA_WATCHDOG_MAX_FAILS:-6}" ]; then
            echo "[entrypoint] Server not answering /health ${fails}x - exiting so the container restarts."
            kill -TERM "$UVICORN_PID" 2>/dev/null || true
            exit 1
        fi
    done
    wait "$UVICORN_PID"
else
    echo "[entrypoint] Starting API server..."
    exec uvicorn adapta.api.app:app \
        --host "${ADAPTA_HOST:-0.0.0.0}" \
        --port "${ADAPTA_PORT:-8000}" \
        --workers "${ADAPTA_WORKERS:-1}"
fi
