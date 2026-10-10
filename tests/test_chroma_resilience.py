"""
E1.15 — a hung or churned Chroma must not leak sockets, block forever, or fail silently.

No real Chroma: a tiny in-process HTTP stub answers the endpoints chromadb 1.5.9's client
calls on construction, and can be told to stall one route so the request timeout is real.
"""

import asyncio
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from adapta.config import settings
from adapta.core.health import HealthMonitor, HealthStatus
from adapta.domain.errors import Timeout, VectorStoreFailed
from adapta.services import rag as rag_mod
from adapta.services.rag import RAGService
from adapta.worker import main as worker_main


class _Chroma:
    """Stub Chroma server; ``stall_seconds`` delays POSTs to a collections route."""

    def __init__(self) -> None:
        self.stall_seconds = 0.0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _reply(self) -> None:
                if self.command == "POST" and "collections" in self.path and stub.stall_seconds:
                    time.sleep(stub.stall_seconds)
                if "pre-flight" in self.path:
                    body = {"max_batch_size": 100}
                elif "identity" in self.path:
                    body = {"user_id": "x", "tenant": "default_tenant", "databases": ["default_database"]}
                elif "collections" in self.path:
                    body = []
                else:
                    body = {"id": "x", "name": "default_database", "tenant": "default_tenant"}
                data = json.dumps(body).encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError:  # the client timed out and hung up
                    pass

            do_GET = do_POST = _reply

            def log_message(self, *args) -> None:  # noqa: D401 - silence
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def chroma(monkeypatch):
    stub = _Chroma()
    monkeypatch.setattr(settings, "chroma_host", "127.0.0.1")
    monkeypatch.setattr(settings, "chroma_port", stub.port)
    rag_mod._reset_chroma_client()
    yield stub
    rag_mod._reset_chroma_client()
    stub.close()


def _open_fds() -> int:
    return len(os.listdir("/proc/self/fd"))


# ---------------------------------------------------------------------------
# (1) leak: one client per process
# ---------------------------------------------------------------------------


def test_one_client_per_process(chroma):
    first = rag_mod._get_chroma_client()
    assert all(rag_mod._get_chroma_client() is first for _ in range(20))


def test_repeated_calls_do_not_grow_open_fds(chroma):
    svc = RAGService()
    svc._client().list_collections()  # warm: the one-time client + its connection pool
    before = _open_fds()
    for _ in range(100):
        svc._client().list_collections()
    # Before E1.15 this grew by ~4 per call (a new HttpClient + sockets each time).
    assert _open_fds() - before <= 4


def test_client_is_shared_across_threads(chroma):
    seen: list = []
    threads = [
        threading.Thread(target=lambda: seen.append(rag_mod._get_chroma_client())) for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({id(c) for c in seen}) == 1


# ---------------------------------------------------------------------------
# (2) request timeout
# ---------------------------------------------------------------------------


def test_request_timeout_is_applied_to_the_session(chroma, monkeypatch):
    monkeypatch.setattr(settings, "chroma_timeout_seconds", 7)
    client = rag_mod._get_chroma_client()
    assert client._server._session.timeout.read == 7


def test_stalled_chroma_raises_typed_error_within_the_timeout(chroma, monkeypatch):
    monkeypatch.setattr(settings, "chroma_timeout_seconds", 1)
    chroma.stall_seconds = 5
    started = time.perf_counter()
    with pytest.raises(VectorStoreFailed) as err:
        RAGService().ensure_collection("proj-1")
    assert time.perf_counter() - started < 4
    assert "did not answer within 1 s" in err.value.message  # lands in error_message


# ---------------------------------------------------------------------------
# (3) job-level deadline
# ---------------------------------------------------------------------------


async def _hang(file_id, *, final):
    await asyncio.sleep(30)


async def test_first_timeout_is_a_transient_retry(monkeypatch):
    monkeypatch.setattr("adapta.api.v1.files.index_file_by_id", _hang)
    monkeypatch.setattr(settings, "index_job_timeout_seconds", 0.05)
    assert await worker_main._index_attempt("f1", final=False) is True


async def test_final_timeout_fails_the_file_with_a_clear_message(monkeypatch):
    failed: dict = {}

    async def fake_fail(file_id, message):
        failed[file_id] = message

    monkeypatch.setattr("adapta.api.v1.files.index_file_by_id", _hang)
    monkeypatch.setattr(worker_main, "_fail_file", fake_fail)
    monkeypatch.setattr(settings, "index_job_timeout_seconds", 0.05)
    with pytest.raises(Timeout):
        await worker_main._index_attempt("f1", final=True)
    assert "timed out" in failed["f1"]
    assert "/health/deep" in failed["f1"]


async def test_index_job_retries_once_then_fails_and_worker_survives(monkeypatch):
    calls: list = []

    async def hang(file_id, *, final):
        calls.append(final)
        await asyncio.sleep(30)

    class Queue:
        statuses: list = []

        async def update_status(self, job_id, **kw):
            self.statuses.append(kw["status"])

    async def noop_fail(file_id, message):
        return None

    queue = Queue()
    monkeypatch.setattr("adapta.api.v1.files.index_file_by_id", hang)
    monkeypatch.setattr(worker_main, "get_job_queue", lambda: queue)
    monkeypatch.setattr(worker_main, "_fail_file", noop_fail)
    monkeypatch.setattr(settings, "index_job_timeout_seconds", 0.05)
    with pytest.raises(Timeout):  # the worker loop turns this into a `failed` job
        await worker_main._run_index_job({"job_id": "j1", "payload": {"id": "f1"}})
    assert calls == [False, True]
    assert queue.statuses == ["running"]


# ---------------------------------------------------------------------------
# (5) /health/deep reports latency
# ---------------------------------------------------------------------------


class _FakeClient:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    def heartbeat(self):
        time.sleep(self.delay)
        return 1


async def test_health_reports_chroma_latency(monkeypatch):
    monkeypatch.setattr(rag_mod, "_get_chroma_client", lambda: _FakeClient(0.02))
    check = await HealthMonitor().check_chroma()
    assert check.status is HealthStatus.HEALTHY
    assert check.details["latency_ms"] >= 20
    assert "ms" in check.message


async def test_health_marks_slow_chroma_degraded(monkeypatch):
    monkeypatch.setattr(rag_mod, "_get_chroma_client", lambda: _FakeClient(0.05))
    monkeypatch.setattr(settings, "chroma_slow_ms", 10)
    assert (await HealthMonitor().check_chroma()).status is HealthStatus.DEGRADED


async def test_health_marks_hung_chroma_unhealthy_without_hanging(monkeypatch):
    monkeypatch.setattr(rag_mod, "_get_chroma_client", lambda: _FakeClient(1.0))
    monkeypatch.setattr(settings, "rag_timeout_seconds", 0.1)
    started = time.perf_counter()
    check = await HealthMonitor().check_chroma()
    assert time.perf_counter() - started < 0.8
    assert check.status is HealthStatus.UNHEALTHY
