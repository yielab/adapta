"""Unit tests for the single base-model catalog (A3.3).

The catalog unifies the two meanings of ``base_model``: a HF repo id (training/eval)
and a GGUF serving name, declared once per entry. These tests do not load any model
— they verify resolution, validation, and that the catalog and the serving
``model_manager`` agree on the GGUF path so the two can never drift.
"""

from __future__ import annotations

import brain.core.model_catalog as mc
from brain.core.model_manager import ModelManager


def test_allowed_names_nonempty_and_unique():
    names = mc.allowed_names()
    assert names, "catalog must declare at least one base model"
    assert len(names) == len(set(names)), "operator-facing names must be unique"


def test_resolve_by_operator_name():
    entry = mc.resolve("qwen2.5-3b-instruct")
    assert entry is not None
    assert entry.hf_repo_id == "Qwen/Qwen2.5-3B-Instruct"


def test_resolve_by_hf_id():
    # A base_model stored as a HF repo id still resolves to the same entry.
    entry = mc.resolve("Qwen/Qwen2.5-3B-Instruct")
    assert entry is not None
    assert entry.name == "qwen2.5-3b-instruct"


def test_unknown_is_invalid():
    assert mc.resolve("definitely-not-a-model") is None
    assert mc.is_valid("definitely-not-a-model") is False


def test_resolve_hf_id_for_training():
    assert mc.resolve_hf_id("qwen2.5-7b-instruct") == "Qwen/Qwen2.5-7B-Instruct"
    # HF id passes through unchanged.
    assert mc.resolve_hf_id("Qwen/Qwen2.5-7B-Instruct") == "Qwen/Qwen2.5-7B-Instruct"
    # Unknown values pass through (dev: direct HF id / local path).
    assert mc.resolve_hf_id("some/local-checkpoint") == "some/local-checkpoint"


def test_resolve_serving_name_maps_hf_to_gguf():
    # The serving (GGUF) name resolves from either the operator name or the HF id.
    assert mc.resolve_serving_name("Qwen/Qwen2.5-0.5B-Instruct") == "qwen2.5-0.5b-instruct"
    assert mc.resolve_serving_name("qwen2.5-0.5b-instruct") == "qwen2.5-0.5b-instruct"
    assert mc.resolve_serving_name("unknown") == "unknown"


def test_catalog_and_model_manager_gguf_paths_agree():
    """Every catalog entry must point at the same GGUF the serving manager loads,
    so a project validated at creation actually serves."""
    mm = ModelManager()
    for entry in mc.all_entries():
        cfg = mm.get_model_config(entry.name)
        assert cfg is not None, f"no serving config for catalog entry {entry.name}"
        assert cfg.path == entry.gguf_path(), (
            f"catalog/model_manager GGUF path drift for {entry.name}: "
            f"{entry.gguf_path()} != {cfg.path}"
        )


def test_model_manager_resolves_hf_id_through_catalog():
    mm = ModelManager()
    # A fine-tune project that stored the HF id resolves to the GGUF serving name.
    assert mm._resolve_serving_name("Qwen/Qwen2.5-3B-Instruct") == "qwen2.5-3b-instruct"
    # Direct serving names pass through.
    assert mm._resolve_serving_name("qwen2.5-3b-instruct") == "qwen2.5-3b-instruct"
