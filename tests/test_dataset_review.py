"""D6 dataset review — unit tests for _read_jsonl and curate validation flow.

These are offline tests (no DB, no HTTP stack) that verify the two new helper
functions introduced for the dataset review surface: the JSONL reader used by
GET /rows, and the validate-then-persist flow used by POST /curate.
"""

import json
from pathlib import Path

from adapta.api.v1.datasets import _read_jsonl
from adapta.services.training import validate_dataset

# ── _read_jsonl ─────────────────────────────────────────────────────────────


def test_read_jsonl_returns_all_rows(tmp_path):
    p = tmp_path / "ds.jsonl"
    rows = [{"prompt": f"Q{i}", "response": f"A{i}"} for i in range(5)]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert _read_jsonl(str(p)) == rows


def test_read_jsonl_skips_blank_lines(tmp_path):
    p = tmp_path / "ds.jsonl"
    p.write_text(
        json.dumps({"prompt": "Q", "response": "A"})
        + "\n\n"
        + json.dumps({"prompt": "Q2", "response": "A2"})
        + "\n"
    )
    result = _read_jsonl(str(p))
    assert len(result) == 2
    assert result[0]["prompt"] == "Q"
    assert result[1]["prompt"] == "Q2"


def test_read_jsonl_empty_file(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    assert _read_jsonl(str(p)) == []


def test_read_jsonl_single_row(tmp_path):
    p = tmp_path / "one.jsonl"
    row = {"prompt": "Hello?", "response": "World."}
    p.write_text(json.dumps(row) + "\n")
    assert _read_jsonl(str(p)) == [row]


def test_read_jsonl_preserves_unicode(tmp_path):
    p = tmp_path / "unicode.jsonl"
    row = {"prompt": "日本語", "response": "テスト"}
    p.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    assert _read_jsonl(str(p)) == [row]


def test_read_jsonl_preserves_arbitrary_fields(tmp_path):
    p = tmp_path / "dpo.jsonl"
    row = {"prompt": "Q?", "chosen": "A.", "rejected": "B.", "system": "Be helpful."}
    p.write_text(json.dumps(row) + "\n")
    assert _read_jsonl(str(p)) == [row]


# ── curate validate flow ─────────────────────────────────────────────────────
# The curate handler writes the kept rows to a temp JSONL and calls
# validate_dataset on it before persisting. These tests exercise that path
# directly (the HTTP layer is covered by integration tests).


def _make_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_curate_valid_sft_rows_pass_validation(tmp_path):
    rows = [{"prompt": f"Q{i}?", "response": f"A{i}."} for i in range(12)]
    p = tmp_path / "curated.jsonl"
    _make_jsonl(p, rows)
    is_valid, error, num_samples, _ = validate_dataset(p)
    assert is_valid, error
    assert num_samples == 12


def test_curate_valid_dpo_rows_pass_validation(tmp_path):
    rows = [{"prompt": f"Q{i}?", "chosen": f"C{i}.", "rejected": f"R{i}."} for i in range(15)]
    p = tmp_path / "curated_dpo.jsonl"
    _make_jsonl(p, rows)
    is_valid, error, num_samples, _ = validate_dataset(p)
    assert is_valid, error
    assert num_samples == 15


def test_curate_invalid_rows_fail_validation(tmp_path):
    rows = [{"prompt": "", "response": ""}]  # blank prompt/response
    p = tmp_path / "bad.jsonl"
    _make_jsonl(p, rows)
    is_valid, error, _, _ = validate_dataset(p)
    assert not is_valid
    assert error


def test_curate_empty_file_fails_validation(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("\n")
    is_valid, error, _, _ = validate_dataset(p)
    assert not is_valid


def test_curate_mixed_sft_dpo_fails_validation(tmp_path):
    rows = [
        {"prompt": "Q1?", "response": "R1."},
        {"prompt": "Q2?", "chosen": "C.", "rejected": "R."},
    ]
    p = tmp_path / "mixed.jsonl"
    _make_jsonl(p, rows)
    is_valid, error, _, _ = validate_dataset(p)
    assert not is_valid
    assert "mix" in error.lower()


def test_curate_subset_of_rows_passes(tmp_path):
    """Simulates a typical review: 20 rows uploaded, 14 kept after dropping 6."""
    original = [{"prompt": f"Q{i}?", "response": f"A{i}."} for i in range(20)]
    kept = [r for i, r in enumerate(original) if i not in {2, 5, 7, 11, 14, 17}]
    assert len(kept) == 14

    p = tmp_path / "subset.jsonl"
    _make_jsonl(p, kept)
    is_valid, error, num_samples, _ = validate_dataset(p)
    assert is_valid, error
    assert num_samples == 14


def test_curate_edited_rows_validated_correctly(tmp_path):
    """Simulates an inline edit: the edited row replaces the original content."""
    edited = {"prompt": "What is the capital of France?", "response": "Paris."}
    rows = [edited, {"prompt": "Q2?", "response": "A2."}] * 6  # 12 rows total
    p = tmp_path / "edited.jsonl"
    _make_jsonl(p, rows)
    is_valid, error, num_samples, _ = validate_dataset(p)
    assert is_valid, error
    assert num_samples == 12
