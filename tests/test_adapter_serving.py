"""Unit tests for fine-tune adapter serving wiring (A3.1).

These do NOT load a real model or run a GPU — they verify the plumbing that makes
a fine-tune endpoint apply its LoRA adapter: cache keying, name resolution, request
threading, and the conversion module's typed-error behavior. The real base+LoRA
inference is covered by the opt-in GPU e2e (tests/integration/test_lora_e2e.py).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from brain.core.inference import InferenceRequest, Message
from brain.core.model_manager import ModelManager


def test_inference_request_carries_adapter_path():
    req = InferenceRequest(
        messages=[Message(role="user", content="hi")],
        model_name="qwen2.5-0.5b-instruct",
        adapter_path="/data/adapters/abc/adapter.gguf",
    )
    assert req.adapter_path == "/data/adapters/abc/adapter.gguf"
    # Default (RAG/base) is None.
    assert InferenceRequest(messages=[], model_name="x").adapter_path is None


def test_cache_key_includes_adapter_so_base_and_finetune_dont_collide():
    mm = ModelManager()
    base_key = mm._cache_key("qwen2.5-0.5b-instruct", None)
    lora_key = mm._cache_key("qwen2.5-0.5b-instruct", "/a/adapter.gguf")
    other_lora = mm._cache_key("qwen2.5-0.5b-instruct", "/b/adapter.gguf")
    assert base_key != lora_key, "base and base+LoRA must not share a cache slot"
    assert lora_key != other_lora, "different adapters must not share a cache slot"
    assert base_key == "qwen2.5-0.5b-instruct"


def test_resolve_serving_name_maps_hf_id_to_gguf_catalog():
    mm = ModelManager()
    # A fine-tune Project stores a HF repo id; serving must resolve it to a GGUF entry.
    assert mm._resolve_serving_name("Qwen/Qwen2.5-0.5B-Instruct") == "qwen2.5-0.5b-instruct"
    # A direct catalog name passes through unchanged.
    assert mm._resolve_serving_name("qwen2.5-3b-instruct") == "qwen2.5-3b-instruct"
    # Unknown names pass through (surfaced later as a clear load error).
    assert mm._resolve_serving_name("totally-unknown") == "totally-unknown"


def test_load_model_rejects_unknown_base():
    mm = ModelManager()
    with pytest.raises(ValueError):
        asyncio.run(mm.load_model("totally-unknown"))


def test_conversion_raises_typed_error_when_no_adapter(tmp_path: Path):
    from brain.core.adapter_conversion import convert_peft_to_gguf
    from brain.domain.errors import AdapterConversionFailed

    empty = tmp_path / "adapter"
    empty.mkdir()
    with pytest.raises(AdapterConversionFailed):
        asyncio.run(convert_peft_to_gguf(empty, base_model_id="Qwen/Qwen2.5-0.5B-Instruct"))


def test_conversion_is_idempotent_when_gguf_exists(tmp_path: Path):
    from brain.core.adapter_conversion import convert_peft_to_gguf, converted_gguf_path

    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_config.json").write_text("{}")
    out = converted_gguf_path(adapter)
    out.write_text("preexisting")  # pretend a prior conversion succeeded
    result = asyncio.run(convert_peft_to_gguf(adapter, base_model_id="Qwen/Qwen2.5-0.5B-Instruct"))
    assert result == out
    assert out.read_text() == "preexisting"  # not re-converted
