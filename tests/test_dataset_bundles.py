"""Image dataset bundles (§V2) — extraction safety, validation, provenance.

Offline unit tests: tiny zips/PNGs are generated in tmp_path with Pillow.
"""

import json
import zipfile

import pytest
from PIL import Image

from adapta.services.training import BundleError, extract_bundle, validate_dataset
from adapta.training.provenance import dataset_manifest_sha256


def _png(path, size=(8, 8), color=(200, 30, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def _bundle(tmp_path, rows, images=(), name="bundle.zip", manifest="data.jsonl", extra=None):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / manifest).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    for rel in images:
        _png(src / rel)
    zpath = tmp_path / name
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.write(src / manifest, manifest)
        for rel in images:
            zf.write(src / rel, rel)
        for arcname, data in (extra or {}).items():
            zf.writestr(arcname, data)
    return zpath


ROWS = [{"prompt": "What is this?", "response": "The emblem.", "images": ["images/a.png"]}]


def test_bundle_happy_path_validates_with_image_counts(tmp_path):
    zpath = _bundle(tmp_path, ROWS, images=["images/a.png"])
    manifest = extract_bundle(zpath, tmp_path / "out")
    valid, error, n, n_img = validate_dataset(manifest, bundle_dir=tmp_path / "out")
    assert valid, error
    assert (n, n_img) == (1, 1)


def test_bundle_zip_slip_rejected(tmp_path):
    zpath = _bundle(tmp_path, ROWS, images=["images/a.png"], extra={"../evil.png": b"x"})
    with pytest.raises(BundleError, match="Unsafe path"):
        extract_bundle(zpath, tmp_path / "out")


def test_bundle_disallowed_file_type_rejected(tmp_path):
    zpath = _bundle(tmp_path, ROWS, images=["images/a.png"], extra={"run.sh": b"#!/bin/sh"})
    with pytest.raises(BundleError, match="Disallowed file type"):
        extract_bundle(zpath, tmp_path / "out")


def test_bundle_must_have_exactly_one_manifest(tmp_path):
    zpath = _bundle(tmp_path, ROWS, images=["images/a.png"], extra={"second.jsonl": b"{}"})
    with pytest.raises(BundleError, match="exactly one root .jsonl"):
        extract_bundle(zpath, tmp_path / "out")


def test_bundle_file_count_cap(tmp_path, monkeypatch):
    from adapta.config import settings

    monkeypatch.setattr(settings, "max_bundle_files", 2)
    zpath = _bundle(tmp_path, ROWS, images=["images/a.png", "images/b.png", "images/c.png"])
    with pytest.raises(BundleError, match="at most 2"):
        extract_bundle(zpath, tmp_path / "out")


def test_missing_image_reference_invalidates_row(tmp_path):
    rows = [{"prompt": "Q?", "response": "A.", "images": ["images/missing.png"]}]
    zpath = _bundle(tmp_path, rows, images=["images/a.png"])
    manifest = extract_bundle(zpath, tmp_path / "out")
    valid, error, _, _ = validate_dataset(manifest, bundle_dir=tmp_path / "out")
    assert not valid
    assert "not found" in error


def test_corrupt_image_invalidates_row(tmp_path):
    zpath = _bundle(tmp_path, ROWS, extra={"images/a.png": b"not a png"})
    manifest = extract_bundle(zpath, tmp_path / "out")
    valid, error, _, _ = validate_dataset(manifest, bundle_dir=tmp_path / "out")
    assert not valid
    assert "cannot be decoded" in error


def test_validation_reports_all_bad_rows_at_once(tmp_path):
    """Enterprise upload: every problem is reported in one pass, not one re-upload
    at a time. Three rows each reference a missing image — all three must show."""
    rows = [
        {"prompt": "Q1?", "response": "A1.", "images": ["images/m1.png"]},
        {"prompt": "Q2?", "response": "A2.", "images": ["images/m2.png"]},
        {"prompt": "Q3?", "response": "A3.", "images": ["images/m3.png"]},
    ]
    zpath = _bundle(tmp_path, rows, images=["images/a.png"])
    manifest = extract_bundle(zpath, tmp_path / "out")
    valid, error, _, _ = validate_dataset(manifest, bundle_dir=tmp_path / "out")
    assert not valid
    assert "Found 3 problem(s)" in error
    for ln in ("Line 1", "Line 2", "Line 3"):
        assert ln in error


def test_validation_error_report_is_capped(tmp_path):
    """A wholly-malformed manifest is summarized, not dumped in full."""
    from adapta.services.training import MAX_REPORTED_ERRORS

    rows = [{"prompt": "", "response": ""} for _ in range(MAX_REPORTED_ERRORS + 10)]
    # Plain .jsonl path (no images) — empty prompt/response on every line.
    manifest = tmp_path / "data.jsonl"
    manifest.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    valid, error, _, _ = validate_dataset(manifest)
    assert not valid
    assert "and" in error and "more" in error  # truncation notice present


def test_validation_counts_only_good_rows(tmp_path):
    """A valid file still reports the right sample/image counts after the refactor."""
    rows = [
        {"prompt": "Q1?", "response": "A1.", "images": ["images/a.png"]},
        {"prompt": "Q2?", "response": "A2.", "images": ["images/b.png"]},
    ]
    zpath = _bundle(tmp_path, rows, images=["images/a.png", "images/b.png"])
    manifest = extract_bundle(zpath, tmp_path / "out")
    valid, error, n, n_img = validate_dataset(manifest, bundle_dir=tmp_path / "out")
    assert valid, error
    assert (n, n_img) == (2, 2)


def test_manifest_hash_changes_with_image_bytes(tmp_path):
    """§V2.3 — the provenance hash must cover image content, not just the JSONL."""
    zpath = _bundle(tmp_path, ROWS, images=["images/a.png"])
    out = tmp_path / "out"
    manifest = extract_bundle(zpath, out)
    h1 = dataset_manifest_sha256(manifest, bundle_dir=out)
    _png(out / "images/a.png", color=(0, 0, 255))  # repaint one image
    h2 = dataset_manifest_sha256(manifest, bundle_dir=out)
    assert h1 and h2 and h1 != h2
    # And the text-only hash (no bundle) ignores images entirely.
    assert dataset_manifest_sha256(manifest) != h1


# ── DPO dataset validation (D4) ────────────────────────────────────────────


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_dpo_rows_validate_ok(tmp_path):
    p = tmp_path / "dpo.jsonl"
    _write_jsonl(p, [
        {"prompt": "Capital of France?", "chosen": "Paris.", "rejected": "Lyon."},
        {"prompt": "Sky colour?", "chosen": "Blue.", "rejected": "Green."},
    ])
    valid, error, n, n_img = validate_dataset(p)
    assert valid, error
    assert n == 2
    assert n_img == 0


def test_dpo_rows_with_system_validate_ok(tmp_path):
    p = tmp_path / "dpo_sys.jsonl"
    _write_jsonl(p, [
        {"prompt": "Q?", "chosen": "A.", "rejected": "B.", "system": "You are helpful."},
    ])
    valid, error, n, _ = validate_dataset(p)
    assert valid, error
    assert n == 1


def test_dpo_missing_chosen_rejected(tmp_path):
    p = tmp_path / "bad_dpo.jsonl"
    _write_jsonl(p, [
        {"prompt": "Q?", "chosen": "A."},  # missing rejected
    ])
    valid, error, _, _ = validate_dataset(p)
    assert not valid
    assert "rejected" in error.lower()


def test_dpo_empty_chosen(tmp_path):
    p = tmp_path / "empty_chosen.jsonl"
    _write_jsonl(p, [
        {"prompt": "Q?", "chosen": "  ", "rejected": "B."},
    ])
    valid, error, _, _ = validate_dataset(p)
    assert not valid
    assert "chosen" in error.lower()


def test_mixed_sft_dpo_rejected(tmp_path):
    p = tmp_path / "mixed.jsonl"
    _write_jsonl(p, [
        {"prompt": "Q1?", "response": "R1."},           # SFT row
        {"prompt": "Q2?", "chosen": "A.", "rejected": "B."},  # DPO row
    ])
    valid, error, _, _ = validate_dataset(p)
    assert not valid
    assert "mix" in error.lower()


def test_sft_rows_still_validate_ok(tmp_path):
    p = tmp_path / "sft.jsonl"
    _write_jsonl(p, [
        {"prompt": "Tell me about France.", "response": "France is in Europe."},
    ])
    valid, error, n, _ = validate_dataset(p)
    assert valid, error
    assert n == 1
