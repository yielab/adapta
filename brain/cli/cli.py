"""Brain From Cero CLI — management helpers."""

import subprocess
import sys

import click


@click.group()
def main():
    """Brain From Cero — self-hosted RAG + LoRA model-customization platform."""


@main.command()
def health():
    """Check liveness of the running server."""
    import httpx

    base = "http://localhost:8000"
    try:
        resp = httpx.get(f"{base}/health", timeout=5)
        data = resp.json()
        click.echo(f"status: {data.get('status', 'unknown')}")
        if resp.status_code != 200:
            sys.exit(1)
    except Exception as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)


@main.command()
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8000, show_default=True)
@click.option("--reload", is_flag=True, default=False)
def serve(host, port, reload):
    """Start the API server with uvicorn."""
    cmd = [
        sys.executable, "-m", "uvicorn",
        "brain.api.app:app",
        "--host", host,
        "--port", str(port),
    ]
    if reload:
        cmd.append("--reload")
    subprocess.run(cmd, check=True)


@main.command()
@click.option("--revision", default="head", show_default=True, help="Alembic revision target")
def migrate(revision):
    """Run Alembic migrations (upgrade to HEAD by default)."""
    subprocess.run(["alembic", "upgrade", revision], check=True)


@main.command(name="migrate-test")
def migrate_test():
    """Verify migration round-trip: upgrade → downgrade -1 → upgrade."""
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    subprocess.run(["alembic", "downgrade", "-1"], check=True)
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    click.echo("migration round-trip passed")
