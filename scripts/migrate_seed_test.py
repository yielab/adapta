"""Seeded migration round-trip test (Pillar 2 — §1.4).

`make migrate-test` round-trips an EMPTY database, which can't catch a
down-migration that fails (or silently loses/corrupts data) only when tables are
populated — e.g. dropping a column that a constraint depends on, or a type change
that can't recast existing rows.

This seeds a fully-connected graph across every table at `head`, then runs
`downgrade -1 → upgrade head` with that data present, and finally re-seeds to
prove the schema is functional after the round-trip. Run inside the stack:

    docker compose exec app python scripts/migrate_seed_test.py
"""

from __future__ import annotations

import asyncio
import secrets
import subprocess
import uuid
from datetime import datetime, timedelta, timezone

from brain.db import models as m
from brain.db.session import AsyncSessionLocal, engine
from brain.services.auth import hash_password


def _alembic(*args: str) -> None:
    print(f"  alembic {' '.join(args)}")
    subprocess.run(["alembic", *args], check=True)


async def _seed(tag: str) -> None:
    """Insert one connected row per table so a down-migration meets real data."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        org = m.Org(name=f"seed-org-{tag}-{suffix}")
        db.add(org)
        await db.flush()

        team = m.Team(org_id=org.id, name="seed-team")
        db.add(team)
        await db.flush()

        user = m.User(
            org_id=org.id,
            email=f"seed-{tag}-{suffix}@example.dev",
            hashed_password=hash_password("seed-password"),
        )
        db.add(user)
        await db.flush()

        db.add(m.TeamMember(team_id=team.id, user_id=user.id, role=m.Role.admin))

        project = m.Project(
            team_id=team.id,
            name="seed-project",
            type=m.ProjectType.finetune,
            status=m.ProjectStatus.created,
            base_model="qwen2.5-3b",
        )
        db.add(project)
        await db.flush()

        dataset = m.Dataset(
            project_id=project.id,
            name="seed.jsonl",
            storage_path="/tmp/seed.jsonl",
            num_samples=2,
            status=m.DatasetStatus.valid,
        )
        db.add(dataset)
        await db.flush()

        db.add(
            m.TrainingJob(
                project_id=project.id,
                dataset_id=dataset.id,
                status=m.JobStatus.succeeded,
                progress=1.0,
                eval_score=0.71,
                eval_passed=True,
            )
        )

        endpoint = m.Endpoint(
            project_id=project.id,
            slug=f"seed-{suffix}",
            status=m.EndpointStatus.active,
            base_model="qwen2.5-3b",
        )
        db.add(endpoint)
        await db.flush()

        db.add(
            m.ApiKey(
                endpoint_id=endpoint.id,
                name="seed-key",
                key_prefix="brn_seed",
                key_hash="x" * 64,
                is_active=True,
            )
        )
        db.add(
            m.ProjectFile(
                project_id=project.id,
                filename="seed.pdf",
                content_type="application/pdf",
                size_bytes=123,
                storage_path="/tmp/seed.pdf",
                status=m.FileStatus.indexed,
                num_chunks=3,
            )
        )
        db.add(
            m.Collection(
                project_id=project.id,
                chroma_collection_name=f"proj_{project.id}",
                embedding_model="all-MiniLM-L6-v2",
                num_documents=1,
                num_chunks=3,
            )
        )
        db.add(
            m.UsageEvent(
                endpoint_id=endpoint.id,
                day=datetime.now(timezone.utc).date(),
                prompt_tokens=10,
                completion_tokens=20,
                request_count=1,
            )
        )
        db.add(
            m.Invitation(
                org_id=org.id,
                team_id=team.id,
                email=f"invitee-{suffix}@example.dev",
                role=m.Role.viewer,
                token=secrets.token_urlsafe(16),
                status=m.InvitationStatus.pending,
                invited_by=user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        )
        await db.commit()
    print(f"  seeded data ({tag})")


async def main() -> None:
    print("Seeded migration round-trip (Pillar 2 / §1.4):")
    _alembic("upgrade", "head")
    await _seed("pre-downgrade")
    _alembic("downgrade", "-1")  # exercise the down-migration WITH data present
    _alembic("upgrade", "head")
    await _seed("post-roundtrip")  # schema is functional again

    # Reset to a clean migrated-but-empty DB so subsequent CI steps (contract
    # tests) start with no rows and can bootstrap a fresh org via /v1/auth/register.
    _alembic("downgrade", "base")
    _alembic("upgrade", "head")

    await engine.dispose()
    print("✓ seeded migration round-trip verified (DB left clean)")


if __name__ == "__main__":
    asyncio.run(main())
