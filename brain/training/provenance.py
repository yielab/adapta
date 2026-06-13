"""
Training provenance (A4.7).

Records everything needed to reproduce or audit a fine-tune later: the seed, a
content hash of the exact dataset, the base model, and the pinned library
versions. Kept dependency-light (no torch/peft import) so it can be unit-tested
in the lean app image — version lookups use installed-package metadata and return
None when a package isn't present, rather than importing it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

# Libraries whose versions materially affect a training result.
_PROVENANCE_PACKAGES = ("torch", "transformers", "peft", "trl", "datasets", "bitsandbytes")


def _pkg_version(name: str) -> Optional[str]:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None  # not installed (e.g. the lean app image) — record as unknown


def sha256_file(path: Path) -> Optional[str]:
    """SHA-256 of a file's bytes, or None if it can't be read."""
    try:
        h = hashlib.sha256()
        with Path(path).open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def dataset_manifest_sha256(dataset_path: Path, bundle_dir: Optional[Path] = None) -> Optional[str]:
    """Content hash of a dataset INCLUDING any images its rows reference (§V2.3).

    For a text dataset this is the JSONL bytes' hash. For an image bundle the
    hash additionally folds in each referenced image's bytes, in row order, so a
    one-pixel change to any image — or a re-ordering of rows — changes the hash.
    Returns None if the manifest can't be read.
    """
    import json

    base = sha256_file(dataset_path)
    if base is None:
        return None
    if bundle_dir is None:
        return base

    h = hashlib.sha256(base.encode())
    try:
        with Path(dataset_path).open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                for rel in json.loads(line).get("images") or []:
                    h.update(rel.encode())
                    h.update((sha256_file(bundle_dir / rel) or "missing").encode())
    except Exception:
        return None
    return h.hexdigest()


def build_provenance(
    base_model: str, dataset_path: Path, seed: int, bundle_dir: Optional[Path] = None
) -> dict:
    """Assemble the provenance record for a training run.

    ``dataset_path`` should be the EXACT file fed to the trainer (the train split),
    so the hash pins the data actually trained on. For image datasets (§V) pass
    ``bundle_dir`` so the hash covers the referenced image bytes too.
    """
    return {
        "seed": seed,
        "base_model": base_model,
        "dataset_sha256": dataset_manifest_sha256(dataset_path, bundle_dir=bundle_dir),
        "library_versions": {pkg: _pkg_version(pkg) for pkg in _PROVENANCE_PACKAGES},
    }
