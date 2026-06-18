"""
A4.7 — training provenance: seed + dataset hash + library versions.

Pure tests (no GPU/training): the record must pin the exact dataset bytes and the
seed so a run can be reproduced/audited later.
"""

from adapta.training.provenance import build_provenance, sha256_file


def test_dataset_hash_is_content_addressed(tmp_path):
    a = tmp_path / "a.jsonl"
    a.write_text('{"prompt": "Q", "response": "A"}\n')
    b = tmp_path / "b.jsonl"
    b.write_text('{"prompt": "Q", "response": "A"}\n')  # identical bytes
    c = tmp_path / "c.jsonl"
    c.write_text('{"prompt": "Q", "response": "different"}\n')

    assert sha256_file(a) == sha256_file(b)  # same bytes → same hash
    assert sha256_file(a) != sha256_file(c)  # different bytes → different hash


def test_missing_file_hashes_to_none(tmp_path):
    assert sha256_file(tmp_path / "nope.jsonl") is None


def test_build_provenance_records_seed_hash_and_versions(tmp_path):
    ds = tmp_path / "train.jsonl"
    ds.write_text('{"prompt": "Q", "response": "A"}\n')

    prov = build_provenance("Qwen/Qwen2.5-0.5B-Instruct", ds, seed=123)

    assert prov["seed"] == 123
    assert prov["base_model"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert prov["dataset_sha256"] == sha256_file(ds)
    # Version map has an entry per tracked package (value is the version string, or
    # None when that package isn't installed in this image — both are valid).
    assert "torch" in prov["library_versions"]
    assert "peft" in prov["library_versions"]
