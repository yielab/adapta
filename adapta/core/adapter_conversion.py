"""PEFT (safetensors) -> GGUF LoRA conversion for serving (A3.1).

Training emits a HuggingFace PEFT adapter (``adapter_model.safetensors`` +
``adapter_config.json``). Serving is a single llama-cpp runtime that can only
apply a **GGUF-format** LoRA (``Llama(..., lora_path=...)``). This module bridges
the two by invoking llama.cpp's *official* ``convert_lora_to_gguf.py`` as a
subprocess — we deliberately do NOT reimplement the GGUF-LoRA serialization
format (hard constraint #1: don't rewrite engine internals).

The converter is vendored into the worker image (see Dockerfile worker stage) at
``settings.lora_convert_dir`` and needs the ``gguf``/``safetensors``/``torch``
toolchain present in the ``[training]`` extras — so conversion runs in the
**worker** after the eval gate passes, producing ``adapter.gguf`` beside the
safetensors adapter. Serving then loads that GGUF.
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


def _stage_vision_adapter(adapter_dir: Path) -> Path:
    """Stage a VLM adapter for conversion (§V3.4, both V0.3 spike caveats).

    transformers 5.x saves PEFT tensors under the new multimodal path
    ``model.language_model.layers.*``; the pinned converter maps the legacy
    ``model.layers.*``. The canonical adapter stays untouched (PeftModel must
    keep loading it) — a ``_gguf_src/`` staging copy gets the renamed tensors
    plus the adapter_config.
    """
    from safetensors.torch import load_file, save_file

    src = adapter_dir / "adapter_model.safetensors"
    staged = adapter_dir / "_gguf_src"
    staged.mkdir(exist_ok=True)
    tensors = load_file(str(src))
    renamed = {k.replace(".language_model.layers.", ".layers."): v for k, v in tensors.items()}
    save_file(renamed, str(staged / "adapter_model.safetensors"))
    (staged / "adapter_config.json").write_bytes((adapter_dir / "adapter_config.json").read_bytes())
    return staged


async def convert_peft_to_gguf(
    adapter_dir: Path,
    *,
    base_model_id: str,
    force: bool = False,
    vision: bool = False,
) -> Path:
    """Convert a PEFT adapter directory to a GGUF LoRA, returning its path.

    Idempotent: if the GGUF already exists and ``force`` is False, it is returned
    as-is. Raises :class:`AdapterConversionFailed` (typed DomainError) on any
    failure so no raw subprocess output leaks to a client.

    ``base_model_id`` is the HuggingFace repo id of the base the adapter was
    trained against; the converter reads its config to map tensor names. Text
    adapters pass it via ``--base-model-id`` (hub/cached config). Vision
    adapters (``vision=True``, §V3.4) instead use the RAW hub config the
    trainer staged at ``<adapter_dir>/base_config/`` — transformers 5.x's
    AutoConfig re-nests the flat config into ``text_config``, which the
    converter's hub loader can't read — and convert from a staged copy with
    tensor names mapped back to the legacy LM paths (V0.3 caveats).
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
                "it ships only in the worker image"
            ),
        )

    src_dir = adapter_dir
    base_args = ["--base-model-id", base_model_id]
    if vision:
        base_cfg = adapter_dir / "base_config"
        if not (base_cfg / "config.json").exists():
            raise AdapterConversionFailed(
                message="Vision adapter cannot be converted for serving.",
                internal_detail=f"missing staged base config at {base_cfg} (trainer writes it)",
            )
        try:
            src_dir = _stage_vision_adapter(adapter_dir)
        except Exception as exc:
            raise AdapterConversionFailed(
                message="Vision adapter cannot be converted for serving.",
                internal_detail=f"tensor staging failed: {exc}",
            ) from exc
        base_args = ["--base", str(base_cfg)]

    cmd = [
        sys.executable,
        str(script),
        "--outfile",
        str(out_path),
        "--outtype",
        settings.lora_outtype,
        *base_args,
        str(src_dir),
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

    if vision and src_dir != adapter_dir:
        # The staging copy served its purpose; the canonical PEFT adapter stays.
        import shutil

        shutil.rmtree(src_dir, ignore_errors=True)

    logger.info("Converted GGUF LoRA written to %s", out_path)
    return out_path
