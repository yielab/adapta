"""
Unit tests for eval-set synthesis (E4.8, adapta/services/synthesis.py): per-mode parsing,
shape filters, exact + near-duplicate dedup, the end-to-end writer with a stubbed generator
and embedder, and the dataset download handler. No Chroma / DB / model needed.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from adapta.domain.errors import InvalidRequest
from adapta.services import synthesis as syn
from adapta.services.datasets import validate_dataset

CHUNK = {
    "id": "f1_0",
    "filename": "en-vacation-policy.md",
    "page": 2,
    "text": "Employees earn 1.5 vacation days each month and may roll over up to 5 unused days.",
}


# -- parsing ---------------------------------------------------------------


def test_extract_pairs_plain_fenced_and_prose():
    plain = '[{"question": "Q", "answer": "A"}]'
    assert syn._extract_pairs(plain) == [{"question": "Q", "answer": "A"}]
    assert syn._extract_pairs("```json\n" + plain + "\n```") == [{"question": "Q", "answer": "A"}]
    assert syn._extract_pairs("Sure!\n" + plain + "\nDone.") == [{"question": "Q", "answer": "A"}]


def test_extract_pairs_skips_bad_items_and_garbage():
    raw = '[{"question": "Q", "answer": ""}, "junk", {"question": 3, "answer": "A"}, {"question": "G", "answer": "Y"}]'
    assert syn._extract_pairs(raw) == [{"question": "G", "answer": "Y"}]
    assert syn._extract_pairs("no json") == []
    assert syn._extract_pairs("[{not: valid}]") == []


def test_rag_eval_rows_match_golden_format():
    raw = '[{"question": "How many vacation days per month?", "answer": "1.5"}]'
    (key, row), = syn.rag_eval_rows(raw, CHUNK)
    assert key == "How many vacation days per month?"
    assert row == {
        "q": "How many vacation days per month?",
        "expected_file": "en-vacation-policy.md",
        "lang": "en",
        "answer": "1.5",
        "source_chunk_id": "f1_0",
        "expected_page": 2,
    }
    # golden keys the E3.8 harness reads are all present
    assert {"q", "expected_file", "lang"} <= row.keys()


def test_rag_eval_rows_omit_page_when_unknown_and_detect_spanish():
    chunk = {**CHUNK, "page": None, "text": "Los empleados ganan días de vacaciones por cada mes que trabajan en la empresa."}
    (_, row), = syn.rag_eval_rows('[{"question": "¿Cuántos días?", "answer": "1,5"}]', chunk)
    assert "expected_page" not in row
    assert row["lang"] == "es"


def test_behavior_extract_response_is_json_object_of_quoted_values():
    raw = json.dumps(
        [
            {"instruction": "Extract the accrual and rollover.", "fields": {"accrual": "1.5 vacation days", "rollover": "5 unused days"}},
            {"instruction": "Extract the approver.", "fields": {"approver": "the CEO"}},  # not in chunk
            {"instruction": "No fields.", "fields": {}},
        ]
    )
    rows = syn.behavior_rows(raw, CHUNK, "extract")
    assert len(rows) == 1
    prompt, response = rows[0][1]["prompt"], rows[0][1]["response"]
    assert json.loads(response) == {"accrual": "1.5 vacation days", "rollover": "5 unused days"}
    assert prompt.startswith(CHUNK["text"]) and "JSON object only" in prompt


def test_behavior_classify_yes_no_only_and_system():
    raw = json.dumps(
        [
            {"statement": "Employees earn 1.5 days a month.", "label": "Yes"},
            {"statement": "Nothing rolls over.", "label": "no"},
            {"statement": "Maybe?", "label": "maybe"},
        ]
    )
    rows = syn.behavior_rows(raw, CHUNK, "classify", system="Be terse.")
    assert [r["response"] for _, r in rows] == ["yes", "no"]
    assert all(r["system"] == "Be terse." for _, r in rows)
    assert "Answer yes or no." in rows[0][1]["prompt"]


def test_behavior_freeform_does_not_require_quote():
    rows = syn.behavior_rows('[{"question": "Q?", "answer": "anything"}]', CHUNK, "freeform")
    assert len(rows) == 1


# -- dedup -----------------------------------------------------------------


def test_dedup_exact_is_case_and_whitespace_insensitive():
    items = [("What  is X?", {"a": 1}), ("what is x?", {"a": 2}), ("Other", {"a": 3})]
    assert [r["a"] for _, r in syn.dedup_exact(items)] == [1, 3]


def test_near_duplicate_mask_drops_above_threshold_keeps_first():
    vectors = [[1.0, 0.0], [0.99, 0.05], [0.0, 1.0]]  # 2nd ~ 1st (cos > 0.92); 3rd orthogonal
    assert syn.near_duplicate_mask(vectors) == [True, False, True]
    assert syn.near_duplicate_mask([[1.0, 0.0], [0.8, 0.6]]) == [True, True]  # cos 0.8 kept


# -- argument checks -------------------------------------------------------


def test_check_synthesis_args_rejects_bad_input():
    syn.check_synthesis_args("rag_eval", "extract", 3, None)
    syn.check_synthesis_args("behavior", "classify", 3, "http://teacher:8000/v1")
    for args in [
        ("bogus", "extract", 3, None),
        ("behavior", "bogus", 3, None),
        ("rag_eval", "extract", 0, None),
        ("rag_eval", "extract", 3, "file:///etc/passwd"),
    ]:
        with pytest.raises(InvalidRequest):
            syn.check_synthesis_args(*args)


# -- end to end with stubs -------------------------------------------------


class _FakeEmbedder:
    def embed(self, texts, *, kind="passage"):
        # identical vector for any text containing "vacation", so two such questions collapse
        return [[1.0, 0.0] if "vacation" in t.lower() else [0.0, 1.0] for t in texts]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_synthesize_rag_eval_writes_golden_rows_and_dedups(tmp_path, monkeypatch):
    monkeypatch.setattr(syn.settings, "datasets_dir", tmp_path)
    monkeypatch.setattr("adapta.services.embeddings.get_embedding_service", lambda: _FakeEmbedder())

    async def fake_generate(system, user, **kw):
        return json.dumps(
            [
                {"question": "How many vacation days per month?", "answer": "1.5"},
                {"question": "Vacation days earned monthly?", "answer": "1.5"},  # near-dup
                {"question": "Max rollover?", "answer": "5"},
            ]
        )

    monkeypatch.setattr(syn, "_generate", fake_generate)
    path, n = _run(syn.synthesize_from_chunks("p1", [CHUNK], mode="rag_eval"))
    rows = [json.loads(ln) for ln in path.read_text().splitlines()]
    assert n == len(rows) == 2
    assert [r["q"] for r in rows] == ["How many vacation days per month?", "Max rollover?"]
    assert all(r["expected_file"] == "en-vacation-policy.md" for r in rows)


def test_synthesize_behavior_output_passes_dataset_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(syn.settings, "datasets_dir", tmp_path)
    monkeypatch.setattr("adapta.services.embeddings.get_embedding_service", lambda: _FakeEmbedder())

    async def fake_generate(system, user, **kw):
        return '[{"instruction": "Extract the rollover limit.", "fields": {"rollover": "5 unused days"}}]'

    monkeypatch.setattr(syn, "_generate", fake_generate)
    path, n = _run(syn.synthesize_from_chunks("p1", [CHUNK], mode="behavior", task="extract"))
    assert n == 1
    ok, err, count = validate_dataset(path, "extract")
    assert ok, err


# -- download handler ------------------------------------------------------


def test_download_dataset_returns_jsonl_file(tmp_path, monkeypatch):
    from adapta.api.v1 import datasets as api

    f = tmp_path / "ds.jsonl"
    f.write_text('{"prompt": "Q", "response": "A"}\n')
    ds = SimpleNamespace(storage_path=str(f), name="synthesized_behavior_20261010.jsonl")

    async def fake_project(db, pid):
        return SimpleNamespace(team_id="t")

    async def fake_member(db, uid, tid):
        return None

    async def fake_valid(db, pid, did):
        return ds

    monkeypatch.setattr(api, "_get_finetune_project", fake_project)
    monkeypatch.setattr(api, "require_team_member", fake_member)
    monkeypatch.setattr(api, "_get_valid_dataset", fake_valid)
    resp = _run(api.download_dataset("p", "d", current_user=SimpleNamespace(id="u"), db=None))
    assert resp.path == str(f)
    assert resp.media_type == "application/x-ndjson"
    assert resp.filename == "synthesized_behavior_20261010.jsonl"
