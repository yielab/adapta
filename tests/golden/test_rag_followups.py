"""F3.1: does history condensation (E5.3) earn its default? recall@5 on follow-up questions.

Each row of ``tests/fixtures/golden/followups.jsonl`` is ``{history, q, expected_file, lang}``
where ``q`` is ambiguous without the history ("who has to approve that?"). For every row the
harness runs the exact chat path, ``chat._retrieval_queries`` then ``chat._retrieve`` (so
the min-score cut applies), twice:

* ON  - ``condense=True``: the served model rewrites ``q`` (``[condensed, original]``).
* OFF - ``condense=False``: ``q`` alone.

and prints recall@5 / MRR per language plus p50/p95 latency and tokens of the condensation step.
Measurement only: it asserts nothing about ON vs OFF (the default is a human decision).

Lives outside ``tests/integration/`` on purpose: that conftest TRUNCATEs the database at the end
of the session, which would wipe a live stack. This file only creates a scratch project through
the API as the dev admin and deletes it afterwards.

Opt-in: ADAPTA_RUN_GOLDEN_FOLLOWUPS=1 (`make golden-followups`). Needs the live stack (app, worker,
Postgres, Chroma) reachable at ADAPTA_BASE_URL, the embedding model, and the base model's GGUF
under data/models for the in-process condensation call.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import statistics
import time
from pathlib import Path

import httpx
import pytest

from adapta.services.chat import _retrieval_queries, _retrieve
from adapta.services.golden import first_rank, summarize

pytestmark = [pytest.mark.integration, pytest.mark.slow]

skip_unless_optin = pytest.mark.skipif(
    os.environ.get("ADAPTA_RUN_GOLDEN_FOLLOWUPS") != "1",
    reason="follow-up golden set is opt-in; set ADAPTA_RUN_GOLDEN_FOLLOWUPS=1",
)

_GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "golden"
_K = 5
_BASE_URL = os.environ.get("ADAPTA_BASE_URL", "http://localhost:8000")
_EMAIL = os.environ.get("ADAPTA_DEV_EMAIL", "admin@example.com")
_PASSWORD = os.environ.get("ADAPTA_DEV_PASSWORD", "admin12345")
# The project default (settings.default_model); also the model that condenses.
_MODEL = os.environ.get("ADAPTA_FOLLOWUPS_MODEL", "qwen2.5-1.5b-instruct")


def _pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, round(p * (len(s) - 1)))] if s else 0.0


def _table(rows: list[dict], label: str) -> None:
    print(f"\n[{label}]  {'slice':<8} {'n':>3} {f'recall@{_K}':>10} {'MRR':>7}")
    for name, grp in [("all", rows)] + [
        (f"lang={lg}", [r for r in rows if r["lang"] == lg]) for lg in ("en", "es")
    ]:
        s = summarize(grp, _K)
        print(f"        {name:<8} {s['n']:>3} {s['recall']:>10.3f} {s['mrr']:>7.3f}")


@skip_unless_optin
async def test_followup_condensation_on_vs_off():
    rows_in = [
        json.loads(ln)
        for ln in (_GOLDEN / "followups.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    docs = sorted((_GOLDEN / "docs").iterdir())
    assert {r["expected_file"] for r in rows_in} <= {d.name for d in docs}

    from adapta.services.rag import get_rag_service

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=60) as c:
        login = await c.post("/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
        assert login.status_code == 200, login.text
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        me = (await c.get("/v1/auth/me", headers=h)).json()
        proj = await c.post(
            "/v1/projects",
            headers=h,
            json={"name": "golden-followups", "type": "rag", "base_model": _MODEL,
                  "team_id": me["teams"][0]["id"]},
        )
        assert proj.status_code == 201, proj.text
        pid = proj.json()["id"]
        try:
            for d in docs:
                files = {"file": (d.name, io.BytesIO(d.read_bytes()), "text/plain")}
                up = await c.post(f"/v1/projects/{pid}/files", headers=h, files=files)
                assert up.status_code == 202, up.text
            for _ in range(240):
                got = (await c.get(f"/v1/projects/{pid}/files", headers=h)).json()
                if len(got) == len(docs) and all(f["status"] in ("indexed", "failed") for f in got):
                    break
                await asyncio.sleep(1)
            assert all(f["status"] == "indexed" for f in got), got

            rag = get_rag_service()
            await asyncio.to_thread(rag.retrieve, pid, "warm-up", top_k=_K)
            warm = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
                    {"role": "user", "content": "and you?"}]
            await _retrieval_queries(model_name=_MODEL, adapter_path=None, messages=warm,
                                     condense=True)  # load the GGUF outside the timing

            results: dict[str, list[dict]] = {"on": [], "off": []}
            cond_ms: list[float] = []
            cond_pt: list[int] = []
            cond_ct: list[int] = []
            for r in rows_in:
                msgs = [*r["history"], {"role": "user", "content": r["q"]}]
                for mode in ("off", "on"):
                    t0 = time.perf_counter()
                    q, pt, ct, _b, _h = await _retrieval_queries(
                        model_name=_MODEL, adapter_path=None, messages=msgs,
                        condense=(mode == "on"),
                    )
                    ms = (time.perf_counter() - t0) * 1000
                    chunks = await _retrieve(rag, pid, q, _K)
                    rank = first_rank([ch.source for ch in chunks], r["expected_file"])
                    results[mode].append({**r, "rank": rank, "ms": ms, "queries": q})
                    if mode == "on":
                        cond_ms.append(ms)
                        cond_pt.append(pt)
                        cond_ct.append(ct)

            _table(results["off"], "OFF (q alone)")
            _table(results["on"], "ON  (condensed + original)")
            print(f"\ncondensation latency  p50={statistics.median(cond_ms):.0f} ms  "
                  f"p95={_pct(cond_ms, 0.95):.0f} ms  (n={len(cond_ms)}, model={_MODEL})")
            print(f"condensation tokens   prompt mean={statistics.mean(cond_pt):.0f}  "
                  f"completion mean={statistics.mean(cond_ct):.0f}")
            print("\nper-row (rank: None = not in top 5)")
            for off, on in zip(results["off"], results["on"], strict=True):
                print(f"  off={off['rank']} on={on['rank']} [{on['lang']}] {on['q']!r} "
                      f"-> {on['queries']!r}  want {on['expected_file']}")
        finally:
            await c.delete(f"/v1/projects/{pid}", headers=h)
