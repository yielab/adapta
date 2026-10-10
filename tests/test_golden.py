"""RAG gate (E5.2): metric math, golden-set parsing, the noise-tolerant regression rule,
the `rag_eval` worker job, and the post-index hook. No DB, Redis or model needed."""

from __future__ import annotations

import json

import pytest

from adapta.domain.errors import InvalidRequest
from adapta.models.generated import RetrievalQuality, RetrievalSummary
from adapta.services import golden
from adapta.worker import main as worker


def _rows(ranks, ms=10.0):
    return [{"rank": r, "ms": ms} for r in ranks]


# ── metric math ──────────────────────────────────────────────────────────────────────────


def test_first_rank_is_one_based_and_none_when_absent():
    assert golden.first_rank(["a.md", "b.md", "b.md"], "b.md") == 2
    assert golden.first_rank(["a.md"], "z.md") is None
    assert golden.first_rank([], "a.md") is None


def test_summarize_recall_mrr_p50():
    rows = [
        {"rank": 1, "ms": 10.0},
        {"rank": 2, "ms": 30.0},
        {"rank": 6, "ms": 20.0},  # found, but outside top-5: counts for MRR only
        {"rank": None, "ms": 40.0},
    ]
    s = golden.summarize(rows, 5)
    assert s["n"] == 4
    assert s["recall"] == pytest.approx(0.5)
    assert s["mrr"] == pytest.approx((1 + 0.5 + 1 / 6) / 4)
    assert s["p50_ms"] == pytest.approx(25.0)


def test_summarize_empty_is_zero_not_a_crash():
    assert golden.summarize([], 5) == {"n": 0, "recall": 0.0, "mrr": 0.0, "p50_ms": 0.0}


# ── regression rule (noise handling) ─────────────────────────────────────────────────────


def test_judge_first_run_has_no_baseline():
    assert golden.judge(0.9, 20, []) == (None, None, False)


def test_judge_baseline_is_the_median_of_the_last_three_runs():
    # newest first; the 0.50 outlier from 4 runs ago is outside the window.
    baseline, delta, regression = golden.judge(0.95, 20, [0.90, 1.00, 0.95, 0.50])
    assert baseline == 0.95
    assert delta == 0.0
    assert regression is False


def test_one_flipped_question_out_of_20_is_noise():
    _, delta, regression = golden.judge(0.95, 20, [1.0, 1.0, 1.0])
    assert delta == -0.05
    assert regression is False  # exactly one question; strict "worse than -0.05" is required


def test_two_questions_out_of_20_is_a_regression():
    _, delta, regression = golden.judge(0.90, 20, [1.0, 1.0, 1.0])
    assert delta == -0.10
    assert regression is True


def test_small_set_needs_more_than_one_question_to_warn():
    # n=10: one question is 0.10, above the 0.05 floor, yet still just one question.
    assert golden.judge(0.9, 10, [1.0])[2] is False
    assert golden.judge(0.8, 10, [1.0])[2] is True


def test_improvement_never_warns():
    assert golden.judge(1.0, 20, [0.6])[2] is False


# ── golden-set files ─────────────────────────────────────────────────────────────────────


def _jsonl(*rows):
    return "\n".join(json.dumps(r) for r in rows)


def test_parse_questions_accepts_the_rag_eval_synthesis_shape():
    text = _jsonl(
        {
            "q": "How many vacation days?",
            "expected_file": "vacation.md",
            "lang": "en",
            "answer": "2 per month",
            "source_chunk_id": "c1",
            "expected_page": 3,
        }
    )
    assert golden.parse_questions(text + "\n\n") == [
        {"q": "How many vacation days?", "expected_file": "vacation.md", "lang": "en"}
    ]


@pytest.mark.parametrize(
    "text",
    [
        "",  # no questions
        "not json",
        "[1, 2]",
        json.dumps({"expected_file": "a.md"}),  # no q
        json.dumps({"q": "x"}),  # no expected_file
        json.dumps({"q": " ", "expected_file": "a.md"}),
    ],
)
def test_parse_questions_rejects_bad_sets_with_a_typed_error(text):
    with pytest.raises(InvalidRequest):
        golden.parse_questions(text)


def test_parse_questions_caps_the_size():
    rows = [{"q": f"q{i}", "expected_file": "a.md"} for i in range(golden.MAX_QUESTIONS + 1)]
    with pytest.raises(InvalidRequest):
        golden.parse_questions(_jsonl(*rows))


def test_the_offline_golden_fixture_is_a_valid_golden_set():
    from pathlib import Path

    path = Path(__file__).parent / "fixtures" / "golden" / "questions.jsonl"
    assert len(golden.load_questions(path)) >= 1


# ── worker: job kind + summary fields ────────────────────────────────────────────────────


def test_rag_eval_is_a_registered_job_kind():
    assert worker.HANDLERS[golden.GOLDEN_JOB_KIND] is worker._rag_eval_job


async def test_rag_eval_handler_passes_the_run_id_and_marks_the_job(monkeypatch):
    calls = []

    class Q:
        async def update_status(self, job_id, **kw):
            calls.append(("status", job_id, kw["status"]))

    async def fake_process(run_id):
        calls.append(("process", run_id))

    monkeypatch.setattr(worker, "get_job_queue", lambda: Q())
    monkeypatch.setattr(golden, "process_run", fake_process)
    await worker._rag_eval_job({"job_id": "j", "kind": "rag_eval", "payload": {"id": "run-1"}})
    assert calls == [("status", "j", "running"), ("process", "run-1"), ("status", "j", "succeeded")]


async def test_index_job_queues_the_gate_after_a_successful_index(monkeypatch):
    seen = []

    class Q:
        async def update_status(self, job_id, **kw):
            seen.append(kw["status"])

    async def ok(file_id, *, final):
        return False

    async def hook(file_id):
        seen.append(("gate", file_id))

    monkeypatch.setattr("adapta.api.v1.files.index_file_by_id", ok)
    monkeypatch.setattr(worker, "get_job_queue", lambda: Q())
    monkeypatch.setattr(golden, "enqueue_after_index", hook)
    await worker._run_index_job({"job_id": "j", "payload": {"id": "f1"}})
    assert seen == ["running", "succeeded", ("gate", "f1")]


def test_quality_fields_fit_the_retrieval_summary():
    q = RetrievalQuality(
        run_id="r1",
        recall_at_5=0.9,
        mrr=0.8,
        n_questions=20,
        run_at="2026-10-10T00:00:00+00:00",
        baseline_recall=1.0,
        delta=-0.1,
        regression=True,
        running=False,
    )
    s = RetrievalSummary(indexed_chunks=12, quality=q)
    assert s.quality.regression is True and s.quality.delta == -0.1
