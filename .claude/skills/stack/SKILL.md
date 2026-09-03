---
name: stack
description: Run, inspect, and debug the local Adapta stack — bring it up, read logs, exercise the API, run GPU/e2e proofs. Use when something must be observed running rather than unit-tested, or when a container, GPU, or live request is misbehaving.
---

# Live stack

## One stack, one entry point

`make up` (host) = `docker compose up -d --build`, GPU auto-detected, prints URLs.
`make up-cpu` forces the CPU opt-out. `make status` waits for health and prints ports.
`make down` stops it. There is **no dev/prod split** and no shell launcher — the app
image ships the full `[dev]` toolchain and the repo is bind-mounted with hot reload,
so `docker compose exec app make <target>` works immediately.

Dependency change → edit `pyproject.toml` → `make up` (rebuild). Never `pip install`
by hand, on the host or into a container.

## Observing

```
docker compose ps
docker compose logs -f --tail=100 app        # or worker, db, redis, chroma
curl -s localhost:8000/health/deep | jq      # postgres + redis + chroma + disk + memory
curl -s localhost:8000/gpu | jq
```
Seeded dev admin on an empty DB: `admin@example.com` / `admin12345`.
Console SPA: `make console-build`, then serve from the app. Playwright proofs live in
`e2e/*.spec.ts` (host): `make screenshots`.

## Rules that save whole sessions

- **Don't edit repo files while a live or GPU test is running** — watchfiles restarts
  uvicorn and the run dies with a misleading transport error.
- **The worker does not hot-reload.** After changing `adapta/worker/` or
  `adapta/training/`: `docker compose restart worker`.
- **GPU is the default**, reserved by the worker in the base compose file;
  `docker-compose.cpu.yml` is the `!reset` opt-out. Don't invert it.
- **chromadb pip pin and the chroma image version must match** — skew = `KeyError('_type')`
  500s on every index call. `make check-chroma`.
- Real training runs are slow and GPU-bound: run one, watch `docker compose logs -f worker`,
  and don't restart the stack mid-run.
- Debug by reading logs and `/health/deep` first; only then open code, guided by
  `.claude/context/repo-map.md`.
