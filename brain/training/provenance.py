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


def build_provenance(base_model: str, dataset_path: Path, seed: int) -> dict:
    """Assemble the provenance record for a training run.

    ``dataset_path`` should be the EXACT file fed to the trainer (the train split),
    so the hash pins the data actually trained on.
    """
    return {
        "seed": seed,
        "base_model": base_model,
        "dataset_sha256": sha256_file(dataset_path),
        "library_versions": {pkg: _pkg_version(pkg) for pkg in _PROVENANCE_PACKAGES},
    }
