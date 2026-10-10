"""E3.1 fix — _index_file: race-free collection get-or-create, atomic counters,
and orphaned-vector cleanup when the commit after the Chroma upsert fails.

The session is a scripted fake (no Postgres); the SQL-level atomicity itself
(ON CONFLICT DO NOTHING, ``col = col + n``) is proven by the live rag e2e / golden run.
"""

from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from adapta.api.v1 import files as files_mod
from adapta.config import settings
from adapta.db.models import FileStatus
from adapta.services.documents import Chunk


class _Result:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj

    def scalar_one(self):
        return self._obj

    def one(self):
        return self._obj


class _Session:
    """Scripted fake; one shared ``state`` across the main and failure-handling sessions."""

    def __init__(self, state):
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt):
        sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
        self.state["sql"].append(sql)
        if sql.startswith("select") and "project_files" in sql:
            return _Result(self.state["pfile"])
        if sql.startswith("select") and "collections" in sql:
            return _Result(SimpleNamespace(embedding_model=settings.embedding_model, embedding_dim=8))
        if sql.startswith("select") and "contextual_retrieval" in sql:  # E5.1: opt-in OFF
            return _Result(SimpleNamespace(contextual_retrieval=False, base_model="m"))
        return _Result(None)

    def add_all(self, rows):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.state["commits"] += 1
        if self.state["fail_on_commit"] == self.state["commits"]:
            raise self.state.get("fail_with") or RuntimeError("unique violation")


async def _run(monkeypatch, fail_on_commit, final=True, fail_with=None):
    import adapta.db.session as session_mod

    state = {
        "sql": [],
        "commits": 0,
        "fail_on_commit": fail_on_commit,
        "fail_with": fail_with,
        "pfile": SimpleNamespace(status=FileStatus.pending, num_chunks=None, error_message=None),
    }
    calls = {"index": 0, "delete": []}

    class FakeRag:
        def ensure_collection(self, pid):
            return "c"

        def index_chunks(self, pid, fid, chunks):
            calls["index"] += 1
            return len(chunks)

        def delete_file_chunks(self, pid, fid):
            calls["delete"].append((pid, fid))

    monkeypatch.setattr(session_mod, "AsyncSessionLocal", lambda: _Session(state))
    monkeypatch.setattr(files_mod, "get_rag_service", lambda: FakeRag())
    monkeypatch.setattr(
        files_mod, "get_embedding_service", lambda: SimpleNamespace(dimension=8)
    )
    chunks = [Chunk(text="hello", source="a.md", index=0)]
    result = await files_mod._index_file(
        "f1", None, "text/markdown", "a.md", "p1", "t1", chunks, final=final
    )
    state["retry"] = result
    return state, calls


async def test_success_uses_conflict_safe_insert_and_writes_no_counters(monkeypatch):
    state, calls = await _run(monkeypatch, fail_on_commit=None)
    assert any("on conflict" in q and "do nothing" in q for q in state["sql"])
    upd = [q for q in state["sql"] if q.startswith("update collections")]
    assert not upd, "no stored counters: nothing updates collections once the dim is known"
    assert state["pfile"].status == FileStatus.indexed
    assert calls["delete"] == []


async def test_commit_failure_after_upsert_deletes_orphaned_vectors(monkeypatch):
    # commits: 1 processing, 2 collection insert, 3 final -> fail the final one
    state, calls = await _run(monkeypatch, fail_on_commit=3)
    assert calls["index"] == 1
    assert calls["delete"] == [("p1", "f1")]
    assert state["pfile"].status == FileStatus.failed
    assert "unique violation" in state["pfile"].error_message


async def test_failure_before_upsert_does_not_touch_chroma(monkeypatch):
    state, calls = await _run(monkeypatch, fail_on_commit=2)
    assert calls["index"] == 0 and calls["delete"] == []


async def test_transient_failure_on_first_attempt_resets_to_pending_and_asks_for_retry(monkeypatch):
    state, _ = await _run(monkeypatch, fail_on_commit=2, final=False, fail_with=OSError("net"))
    assert state["retry"] is True
    assert state["pfile"].status == FileStatus.pending
    assert state["pfile"].error_message is None


async def test_transient_failure_on_final_attempt_fails_the_file(monkeypatch):
    state, _ = await _run(monkeypatch, fail_on_commit=2, final=True, fail_with=OSError("net"))
    assert state["retry"] is False
    assert state["pfile"].status == FileStatus.failed


async def test_deterministic_failure_is_never_retried(monkeypatch):
    state, _ = await _run(monkeypatch, fail_on_commit=2, final=False)  # RuntimeError
    assert state["retry"] is False
    assert state["pfile"].status == FileStatus.failed
