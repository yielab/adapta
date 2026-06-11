"""Image dataset bundles (§V2) — extraction safety, validation, provenance.

Offline unit tests: tiny zips/PNGs are generated in tmp_path with Pillow.
"""

import json
import zipfile

import pytest
from PIL import Image

from brain.services.training import BundleError, extract_bundle, validate_dataset
from brain.training.provenance import dataset_manifest_sha256


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
    from brain.config import settings
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
