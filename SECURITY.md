# Security Policy

## Supported versions

Adapta is pre-1.0 software. Security fixes are applied to the `main` branch only.

---

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report privately via the [GitHub Security Advisory](https://github.com/yielab/adapta/security/advisories/new) feature. Include:

- A description of the vulnerability and its impact
- Steps to reproduce
- Affected versions / components
- Suggested fix if you have one

You can expect an initial response within 5 business days.

---

## Security model

Adapta is **single-tenant, on-premises software**. Your organization operates the server; no data leaves your infrastructure.

### Authentication

- **Operators** (the console and control-plane API) authenticate via **JWT** issued at `POST /v1/auth/login`. Tokens expire; the secret is set in `.env` (`ADAPTA_SECRET_KEY`).
- **Passwords** are hashed with **bcrypt** (direct bcrypt, SHA-256 pre-hash to handle long inputs). No plaintext passwords are stored.
- **Client applications** authenticate with **scoped `adp_*` API keys**, each bound to a single project endpoint. Keys are bcrypt-hashed in the database; the raw key is shown once at generation time.

### Authorization

- RBAC with two roles: **admin** (full project and team management) and **viewer** (read-only).
- A `adp_*` key cannot drive any endpoint other than the one it was issued for — the auth layer enforces this before any inference runs.

### Network exposure

- By default the stack binds to `localhost:8000` and is not TLS-terminated by the application itself.
- **For any deployment beyond a single developer's laptop:** put Caddy or nginx in front with TLS. A reference `Caddyfile` and `Caddyfile.local` are included.
- Never expose port 8000 directly to the internet.

### CORS

The default `cors_origins` is empty (`[]`) — no cross-origin browser access is allowed out of the box. The operator console is served same-origin from `/console/`, so it needs no CORS entry. If you build a separate browser front-end on another origin, set `ADAPTA_CORS_ORIGINS` explicitly to that origin (never `*`).

### Container hardening

The dev stack (`docker compose up` / `make up`) bind-mounts the repo and runs as root so hot-reload and toolchain writes work freely. A production hardening overlay is shipped at `docker-compose.prod.yml`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The overlay applies to the `app` and `worker` services:

| Control | Setting |
| --- | --- |
| Non-root user | `user: "10001:10001"` (`adapta` system user, uid 10001, created in the base image stage) |
| Linux capabilities | `cap_drop: [ALL]` |
| Privilege escalation | `security_opt: no-new-privileges:true` |
| Root filesystem | `read_only: true` |
| Writable temp | `/tmp` as tmpfs |
| Persistent data | Named volume `app-data` mounted at `/app/data` (uploads, models, adapters, datasets) |
| Model caches | `HF_HOME`, `SENTENCE_TRANSFORMERS_HOME`, `TORCH_HOME` all redirected to `/app/data/.*_cache` |

The dev `docker-compose.yml` is **not modified** — apply the overlay only for production deployments.

### Secrets management

Generate a strong JWT secret before first run:

```bash
sed -i "s|^ADAPTA_SECRET_KEY=.*|ADAPTA_SECRET_KEY=$(openssl rand -hex 32)|" .env
```

Set a strong `POSTGRES_PASSWORD` in `.env`. The `.env` file is gitignored — never commit it.

### Data privacy

Everything is on-premises by design:

- Documents, embeddings (ChromaDB), and training datasets stay on your server.
- Inference (llama-cpp-python) runs locally — no call to any external API.
- No telemetry or analytics are collected.

---

## Security best practices for contributors

1. **Never commit secrets** — API keys, passwords, tokens, or `.env` files.
2. **Never write `raise HTTPException(detail=str(e))`** — use the typed `DomainError` taxonomy in `adapta/domain/errors.py`. The `make check-leaks` CI gate enforces this.
3. **Use parameterized queries** — SQLAlchemy ORM is the only way to touch the database; raw SQL is prohibited.
4. **Validate at system boundaries** — all external inputs are validated by Pydantic models generated from `specs/openapi.yaml`.
5. Run `make check-leaks` before every PR.

---

## Third-party dependencies

Key security-relevant libraries:

| Library | Role |
| --- | --- |
| `bcrypt` | Password hashing |
| `python-jose` | JWT signing / verification |
| `fastapi` | HTTP framework with Pydantic input validation |
| `sqlalchemy` | ORM (parameterized queries) |
| `llama-cpp-python` | Local GGUF inference — no outbound network calls |

Dependency versions are pinned in `pyproject.toml`. To update, edit `pyproject.toml` and rebuild the container — never `pip install` on the host.
