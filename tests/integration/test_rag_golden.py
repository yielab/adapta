"""Retrieval-quality golden set (§E3.8): recall@5, MRR and p50 latency of ``retrieve()``.

Indexes the small bilingual corpus in ``tests/fixtures/golden/docs`` through the
real upload path (so parsing, chunking and embedding are the production ones),
runs every question in ``questions.jsonl`` through ``RAGService.retrieve()``,
prints a table and asserts recall@5 against the ratchet in ``floor.json``.

Opt-in (needs the live stack and the embedding model): ADAPTA_RUN_GOLDEN=1.

Run:  make golden
      ADAPTA_GOLDEN_CONTEXTUAL=1 make golden   # E5.1: project created with contextual_retrieval
                                                # (needs the base model on the worker; the ON/OFF
                                                # comparison is printed, the floor still applies)
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import statistics
import time
from pathlib import Path

import pytest

from adapta.services.rag import get_rag_service

pytestmark = [pytest.mark.integration, pytest.mark.slow]

skip_unless_optin = pytest.mark.skipif(
    os.environ.get("ADAPTA_RUN_GOLDEN") != "1",
    reason="golden retrieval set is opt-in; set ADAPTA_RUN_GOLDEN=1 (or `make golden`)",
)

_GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "golden"
_K = 5
_CONTEXTUAL = os.environ.get("ADAPTA_GOLDEN_CONTEXTUAL") == "1"
# Catalog name only; creating a RAG project does not load the model.
_MODEL_NAME = "qwen2.5-3b-instruct"


def _load_questions() -> list[dict]:
    lines = (_GOLDEN / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(ln) for ln in lines if ln.strip()]


def _first_rank(sources: list[str], expected: str) -> int | None:
    """1-based rank of the first chunk from ``expected``; None when absent."""
    for i, src in enumerate(sources, start=1):
        if src == expected:
            return i
    return None


def _summarize(rows: list[dict]) -> dict:
    n = len(rows)
    hits = sum(1 for r in rows if r["rank"] is not None and r["rank"] <= _K)
    rr = sum(1.0 / r["rank"] for r in rows if r["rank"] is not None)
    return {
        "n": n,
        "recall": hits / n if n else 0.0,
        "mrr": rr / n if n else 0.0,
        "p50_ms": statistics.median(r["ms"] for r in rows) if rows else 0.0,
    }


def _print_table(rows: list[dict]) -> None:
    groups = [("all", rows)] + [
        (f"lang={lang}", [r for r in rows if r["lang"] == lang])
        for lang in sorted({r["lang"] for r in rows})
    ]
    print(f"\n{'slice':<10} {'n':>4} {f'recall@{_K}':>10} {'MRR':>7} {'p50 ms':>8}")
    for name, grp in groups:
        s = _summarize(grp)
        print(f"{name:<10} {s['n']:>4} {s['recall']:>10.3f} {s['mrr']:>7.3f} {s['p50_ms']:>8.1f}")
    misses = [r for r in rows if r["rank"] is None or r["rank"] > _K]
    for r in misses:
        print(f"  MISS rank={r['rank']} expected={r['expected_file']}  q={r['q']!r}")


async def _poll(make_request, ok, tries=180, delay=1.0):
    r = await make_request()
    for _ in range(tries):
        if ok(r):
            return r
        await asyncio.sleep(delay)
        r = await make_request()
    return r


@skip_unless_optin
async def test_golden_retrieval(client, admin, caplog):
    h, team_id = admin["headers"], admin["team_id"]
    questions = _load_questions()
    docs = sorted((_GOLDEN / "docs").iterdir())
    assert len(questions) >= 30 and len(docs) >= 20
    names = {d.name for d in docs}
    assert {q["expected_file"] for q in questions} <= names, "question points at a missing doc"

    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={
            "name": "golden",
            "type": "rag",
            "base_model": _MODEL_NAME,
            "team_id": team_id,
            # Default OFF: the payload gains a field only when the opt-in env var is set.
            **({"contextual_retrieval": True} if _CONTEXTUAL else {}),
        },
    )
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    # Index once through the real upload path, all documents at once: indexing runs as
    # queued worker jobs (E3.7), so concurrency is bounded by the worker, not by the number
    # of uploads in flight.
    index_t0 = time.perf_counter()
    for d in docs:
        files = {"file": (d.name, io.BytesIO(d.read_bytes()), "text/plain")}
        up = await client.post(f"/v1/projects/{pid}/files", headers=h, files=files)
        assert up.status_code == 202, up.text

    def _all_terminal(r):
        return (
            r.status_code == 200
            and len(r.json()) == len(docs)
            and all(f["status"] in ("indexed", "failed") for f in r.json())
        )

    got = await _poll(lambda: client.get(f"/v1/projects/{pid}/files", headers=h), _all_terminal)
    assert _all_terminal(got), f"indexing did not finish: {got.text[:300]}"

    index_s = time.perf_counter() - index_t0
    print(f"\nindexing: {index_s:.1f}s for {len(docs)} docs (contextual_retrieval={_CONTEXTUAL})")
    statuses = {f["filename"]: f["status"] for f in got.json()}
    assert all(s == "indexed" for s in statuses.values()), f"indexing incomplete: {statuses}"

    rag = get_rag_service()
    caplog.set_level(logging.INFO, logger="adapta.services.rag")
    # retrieve() is blocking (and its sparse leg refuses to run on the event loop).
    await asyncio.to_thread(rag.retrieve, pid, "warm-up", top_k=_K)  # load models outside timing

    rows: list[dict] = []
    for q in questions:
        caplog.clear()
        t0 = time.perf_counter()
        chunks = await asyncio.to_thread(rag.retrieve, pid, q["q"], top_k=_K)
        ms = (time.perf_counter() - t0) * 1000
        fts = [
            int(m.group(1))
            for r in caplog.records
            if (m := re.search(r"rag\.retrieve .* fts=(\d+)", r.getMessage()))
        ]
        assert len(fts) == 1, f"expected one rag.retrieve log line, got {len(fts)}"
        rank = _first_rank([c.source for c in chunks], q["expected_file"])
        rows.append({**q, "rank": rank, "ms": ms, "fts": fts[0]})

    with_fts = sum(1 for r in rows if r["fts"] > 0)
    print(f"\nsparse leg contributed on {with_fts}/{len(rows)} questions")
    assert with_fts >= len(rows) // 2, (
        f"FTS leg returned hits for only {with_fts}/{len(rows)} questions; it is not running"
    )

    _print_table(rows)

    floor = json.loads((_GOLDEN / "floor.json").read_text(encoding="utf-8"))["recall_at_5"]
    recall = _summarize(rows)["recall"]
    assert recall >= floor, f"recall@{_K} {recall:.3f} fell below the floor {floor:.3f}"
