"""Development seed: a default admin so the console is usable on first boot.

Runs from the entrypoint after migrations (``python -m brain.db.seed``). Gated by
``BRAIN_SEED_DEFAULT_ADMIN`` (the compose file enables it) and idempotent: it only
acts on an empty database — if any org exists (a previous seed, or an operator's
own ``POST /v1/auth/register``), it does nothing, so it can never clobber or
shadow real accounts.
"""

import asyncio
import logging

from sqlalchemy import func, select

from brain.config import settings
from brain.db.models import Org, Role, Team, TeamMember
from brain.db.session import AsyncSessionLocal, engine
from brain.services.auth import create_user

logger = logging.getLogger("brain.seed")


async def seed_default_admin(session_factory=AsyncSessionLocal) -> bool:
    """Create org/team/admin from the BRAIN_DEFAULT_ADMIN_* settings if the DB is
    empty. Returns True if it seeded, False if it was a no-op.

    Accepts an alternative session factory so callers on their own event loop
    (e.g. the integration-suite teardown) can pass a fresh engine instead of the
    app's shared pooled one.
    """
    async with session_factory() as db:
        org_count = (await db.execute(select(func.count()).select_from(Org))).scalar()
        if org_count and org_count > 0:
            logger.info("Seed skipped: an organization already exists.")
            return False

        org = Org(name=settings.default_admin_org)
        db.add(org)
        await db.flush()

        team = Team(org_id=org.id, name="default")
        db.add(team)
        await db.flush()

        user = await create_user(db, org.id, settings.default_admin_email, settings.default_admin_password)
        db.add(TeamMember(team_id=team.id, user_id=user.id, role=Role.admin))
        await db.commit()

        logger.info("Seeded default admin: %s (org: %s)", user.email, org.name)
        return True


async def _main() -> None:
    if not settings.seed_default_admin:
        logger.info("Seed disabled (BRAIN_SEED_DEFAULT_ADMIN is off).")
        return
    try:
        await seed_default_admin()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[seed] %(message)s")
    asyncio.run(_main())
