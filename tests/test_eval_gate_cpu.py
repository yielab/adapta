"""E4.3 live rung — score the E4.1 fixture adapters on CPU through the serving path.

Opt-in and slow (loads the 0.5B base GGUF, generates per row, adapter and base):

    ADAPTA_RUN_EVAL_CPU=1 pytest tests/test_eval_gate_cpu.py -s

Skips cleanly without the env var or without the base GGUF under ``settings.models_dir``
(``<models_dir>/qwen2.5-0.5b/qwen2.5-0.5b-instruct-q4_k_m.gguf``).
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from adapta.core.model_catalog import resolve
from adapta.services import eval_gate

BASE = "qwen2.5-0.5b-instruct"
FIXTURES = Path(__file__).parent / "fixtures" / "adapters"

pytestmark = pytest.mark.skipif(
    os.environ.get("ADAPTA_RUN_EVAL_CPU") != "1",
    reason="slow CPU eval is opt-in; set ADAPTA_RUN_EVAL_CPU=1",
)


@pytest.fixture(autouse=True)
def _base_gguf():
    entry = resolve(BASE)
    if entry is None or not entry.gguf_path().exists():
        pytest.skip(f"base GGUF not found at {entry.gguf_path() if entry else BASE}")


def _rows(name: str) -> list[dict]:
    path = FIXTURES / name / "dataset_eval.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def _report(name: str, adapter_gguf: str, task: str) -> dict:
    metrics = await eval_gate.evaluate(BASE, adapter_gguf, _rows(name), task)
    print(
        f"\n{name}: adapter={metrics['adapter_score']:.3f} base={metrics['base_score']:.3f} "
        f"rule={metrics['rule']} s/row adapter={metrics['adapter_seconds_per_row']:.2f} "
        f"base={metrics['base_seconds_per_row']:.2f}"
    )
    return metrics


async def test_classification_adapter_passes():
    gguf = FIXTURES / "classify-pass" / "adapter.gguf"
    metrics = await _report("classify-pass", str(gguf), "classify")
    assert metrics["passed"], metrics


async def test_garbage_control_fails(tmp_path):
    from adapta.core import adapter_conversion

    if adapter_conversion._converter_script() is None:
        pytest.skip("control fixture ships no GGUF and the llama.cpp LoRA converter is absent")
    work = tmp_path / "garbage-control"
    shutil.copytree(FIXTURES / "garbage-control", work)
    gguf = await adapter_conversion.convert_peft_to_gguf(
        work, base_model_id="Qwen/Qwen2.5-0.5B-Instruct"
    )
    metrics = await _report("garbage-control", str(gguf), "freeform")
    assert not metrics["passed"], metrics
