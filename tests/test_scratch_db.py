"""F1.2: the scratch-DB name/URL derivation must be idempotent (the Makefile
exports the scratch URL, then calls the helper again)."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "scratch_db", Path(__file__).parent.parent / "scripts" / "scratch_db.py"
)
assert _spec is not None and _spec.loader is not None
scratch_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scratch_db)

LIVE = "postgresql+asyncpg://adapta:pw@postgres:5432/adapta"


def test_scratch_url_appends_suffix_once() -> None:
    first = scratch_db.scratch_url(LIVE)
    assert first.database == "adapta_migrate_test"
    again = scratch_db.scratch_url(first.render_as_string(hide_password=False))
    assert again.database == "adapta_migrate_test"
    assert again.password == "pw"
