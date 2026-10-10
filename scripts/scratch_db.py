"""Throwaway database helper for `make migrate-test` (F1.2).

    python scripts/scratch_db.py name            # print the scratch DB name
    python scripts/scratch_db.py url             # print its SQLAlchemy URL
    python scripts/scratch_db.py create          # (re)create it, empty
    python scripts/scratch_db.py drop            # drop it if present

The scratch DB is `<live db>_migrate_test` on the same server as
`ADAPTA_DATABASE_URL`; it can never equal the live DB.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from adapta.config import settings

SUFFIX = "_migrate_test"


def scratch_url(url: str) -> URL:
    """Scratch URL for `url`; idempotent if `url` already points at the scratch DB."""
    live = make_url(url)
    db = live.database or ""
    return live.set(database=db if db.endswith(SUFFIX) else db + SUFFIX)


_scratch = scratch_url(settings.database_url)
NAME = _scratch.database
# Maintenance connection: the scratch DB itself may not exist yet.
_admin_url = _scratch.set(database="postgres")


async def _admin(sql_fn: Callable[[AsyncConnection], Awaitable[None]]) -> None:
    # CREATE/DROP DATABASE can't run in a transaction -> AUTOCOMMIT, via the
    # maintenance `postgres` database.
    engine = create_async_engine(_admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await sql_fn(conn)
    finally:
        await engine.dispose()


async def _drop(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = :n AND pid <> pg_backend_pid()"
        ),
        {"n": NAME},
    )
    await conn.execute(text(f'DROP DATABASE IF EXISTS "{NAME}"'))


async def _create(conn: AsyncConnection) -> None:
    await _drop(conn)
    await conn.execute(text(f'CREATE DATABASE "{NAME}"'))


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "name":
        print(NAME)
    elif cmd == "url":
        print(_scratch.render_as_string(hide_password=False))
    elif cmd == "create":
        asyncio.run(_admin(_create))
        print(f"  created scratch database {NAME}")
    elif cmd == "drop":
        asyncio.run(_admin(_drop))
        print(f"  dropped scratch database {NAME}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
