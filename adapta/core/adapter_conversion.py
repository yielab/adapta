"""PEFT (safetensors) -> GGUF LoRA conversion for serving.

An adapter arrives as a HuggingFace PEFT directory (``adapter_model.safetensors`` +
``adapter_config.json``). Serving is a single llama-cpp runtime that can only
apply a **GGUF-format** LoRA (``Llama(..., lora_path=...)``). This module bridges
the two by invoking llama.cpp's *official* ``convert_lora_to_gguf.py`` as a
subprocess — we deliberately do NOT reimplement the GGUF-LoRA serialization
format (hard constraint #1: don't rewrite engine internals).

The converter scripts are vendored into the ``app`` image at ``settings.lora_convert_dir``
(Dockerfile, pinned llama.cpp tag) and use the ``gguf``/``safetensors``/``torch`` toolchain
already in the image. The base's ``config.json`` comes from a local directory, never the Hub.
It produces ``adapter.gguf`` beside the safetensors adapter; serving then loads that GGUF.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from adapta.config import settings
from adapta.domain.errors import AdapterConversionFailed

logger = logging.getLogger(__name__)

CONVERT_SCRIPT = "convert_lora_to_gguf.py"


def converted_gguf_path(adapter_dir: Path) -> Path:
    """Where the converted GGUF LoRA lives for a given PEFT adapter directory."""
    return adapter_dir / settings.lora_gguf_filename


def _converter_script() -> Optional[Path]:
    script = settings.lora_convert_dir / CONVERT_SCRIPT
    return script if script.exists() else None


async def convert_peft_to_gguf(
    adapter_dir: Path,
    *,
    base_config_dir: Path,
    force: bool = False,
) -> Path:
    """Convert a PEFT adapter directory to a GGUF LoRA, returning its path.

    Idempotent: if the GGUF already exists and ``force`` is False, it is returned
    as-is. Raises :class:`AdapterConversionFailed` (typed DomainError) on any
    failure so no raw subprocess output leaks to a client.

    ``base_config_dir`` is a local directory holding the base model's HuggingFace
    ``config.json`` (``CatalogEntry.hf_config_dir()``); the converter reads it to map tensor
    names. It always runs with ``--base <dir>`` and never reaches the Hub, so conversion
    works air-gapped.
    """
    adapter_dir = Path(adapter_dir)
    out_path = converted_gguf_path(adapter_dir)

    if out_path.exists() and not force:
        logger.info("GGUF LoRA already present at %s — skipping conversion", out_path)
        return out_path

    if not (adapter_dir / "adapter_config.json").exists():
        raise AdapterConversionFailed(
            message="Adapter cannot be served: no PEFT adapter found.",
            internal_detail=f"missing adapter_config.json in {adapter_dir}",
        )

    script = _converter_script()
    if script is None:
        raise AdapterConversionFailed(
            message="Adapter conversion is unavailable on this node.",
            internal_detail=(
                f"converter {CONVERT_SCRIPT} not found in {settings.lora_convert_dir}; "
                "it is vendored into the app image by the Dockerfile"
            ),
        )

    if not (Path(base_config_dir) / "config.json").exists():
        raise AdapterConversionFailed(
            message="Adapter conversion is unavailable: the base model's config is missing on this node.",
            internal_detail=(
                f"missing {Path(base_config_dir) / 'config.json'}; download the base's config.json "
                "there (see OPERATIONS: air-gapped base configs)"
            ),
        )

    cmd = [
        sys.executable,
        str(script),
        "--outfile",
        str(out_path),
        "--outtype",
        settings.lora_outtype,
        "--base",
        str(base_config_dir),
        str(adapter_dir),
    ]
    logger.info("Converting PEFT adapter -> GGUF LoRA: %s", " ".join(cmd))

    # convert_lora_to_gguf.py does `from convert_hf_to_gguf import ...`; both live in
    # lora_convert_dir, so put that dir on PYTHONPATH for the child so the sibling
    # import resolves regardless of our own cwd.
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        str(settings.lora_convert_dir) + os.pathsep + env.get("PYTHONPATH", "")
    ).rstrip(os.pathsep)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode("utf-8", errors="replace") if stdout else ""

    if proc.returncode != 0 or not out_path.exists():
        raise AdapterConversionFailed(
            message="Failed to convert the fine-tuned adapter for serving.",
            internal_detail=f"converter rc={proc.returncode}; output:\n{output[-4000:]}",
        )

    logger.info("Converted GGUF LoRA written to %s", out_path)
    return out_path
