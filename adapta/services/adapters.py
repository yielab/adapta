"""Static validation + storage of an imported LoRA adapter (E4.2), and the adapter job (E4.4).

An upload is either one GGUF LoRA or a ``.zip`` of a PEFT adapter. The upload path loads
nothing and scores nothing: it proves the file *is* what it claims — extension, magic bytes,
exact zip members, LoRA type, and a base model that matches the project's — and moves it
under ``settings.adapters_dir/{id}/``. Every rejection is an :class:`InvalidAdapter` whose
message names the expected value.

:func:`process_adapter` is the worker-side job (``uploaded -> processing -> passed | failed``):
convert (PEFT), probe-load, score with ``eval_gate``, persist. Heavy imports stay inside it
so the API process never pays for them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import struct
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from adapta.config import settings
from adapta.core import model_catalog
from adapta.db.models import AdapterFormat
from adapta.domain.errors import (
    AdapterIncompatible,
    DomainError,
    InvalidAdapter,
    ModelNotFound,
    PayloadTooLarge,
)

logger = logging.getLogger(__name__)

PEFT_WEIGHTS = "adapter_model.safetensors"
PEFT_CONFIG = "adapter_config.json"
PEFT_MEMBERS = frozenset({PEFT_WEIGHTS, PEFT_CONFIG})
GGUF_FILENAME = "adapter.gguf"
PEFT_SUBDIR = "peft"

_GGUF_MAGIC = b"GGUF"
_ZIP_MAGIC = b"PK\x03\x04"
_CONFIG_MAX_BYTES = 1024 * 1024
_SAFETENSORS_HEADER_MAX = 100 * 1024 * 1024
_COPY_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class StoredAdapter:
    """What a validated upload became on disk."""

    format: AdapterFormat
    base_model: str  # the catalog name of the project's base
    sha256: str  # of the uploaded file
    size_bytes: int
    peft_dir: Optional[Path]
    gguf_path: Optional[Path]


def adapter_dir(adapter_id: str) -> Path:
    return settings.adapters_dir / adapter_id


def remove_adapter_files(adapter_id: str) -> None:
    shutil.rmtree(adapter_dir(adapter_id), ignore_errors=True)


def format_for_filename(filename: str) -> AdapterFormat:
    """``.gguf`` -> gguf, ``.zip`` -> peft; anything else is rejected."""
    lowered = filename.lower()
    if lowered.endswith(".gguf"):
        return AdapterFormat.gguf
    if lowered.endswith(".zip"):
        return AdapterFormat.peft
    raise InvalidAdapter(
        message="Adapter must be a .gguf file (GGUF LoRA) or a .zip holding "
        f"{PEFT_WEIGHTS} and {PEFT_CONFIG} (PEFT LoRA)."
    )


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_COPY_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _accepted_bases(entry: model_catalog.CatalogEntry) -> tuple[str, ...]:
    return (entry.hf_repo_id, *entry.adapter_base_aliases)


def _read_magic(path: Path, n: int) -> bytes:
    with path.open("rb") as f:
        return f.read(n)


# ---------------------------------------------------------------------------
# GGUF
# ---------------------------------------------------------------------------


def _gguf_str(reader, key: str) -> Optional[str]:
    field = reader.fields.get(key)
    if field is None:
        return None
    try:
        value = field.contents()
    except Exception:  # noqa: BLE001 - a malformed field is "not the expected value"
        return None
    return value if isinstance(value, str) else None


def validate_gguf(path: Path, entry: model_catalog.CatalogEntry) -> None:
    """Magic bytes, then ``general.type == adapter``, ``adapter.type == lora`` and the
    architecture of the project's base."""
    if _read_magic(path, 4) != _GGUF_MAGIC:
        raise InvalidAdapter(message="Not a GGUF file: the first 4 bytes must be 'GGUF'.")
    try:
        from gguf import GGUFReader

        reader = GGUFReader(str(path), "r")
    except Exception as exc:  # noqa: BLE001
        raise InvalidAdapter(
            message="The GGUF file could not be parsed; re-export the LoRA adapter.",
            internal_detail=f"GGUFReader failed on {path}: {exc!r}",
        ) from exc

    for key, expected in (("general.type", "adapter"), ("adapter.type", "lora")):
        got = _gguf_str(reader, key)
        if got != expected:
            raise InvalidAdapter(
                message=f"GGUF metadata {key} must be '{expected}' (got {got!r}); "
                "upload a GGUF LoRA adapter, not a full model."
            )
    arch = _gguf_str(reader, "general.architecture")
    if arch != entry.architecture:
        raise InvalidAdapter(
            message=f"GGUF architecture must be '{entry.architecture}' to match base model "
            f"'{entry.name}' (got {arch!r})."
        )


# ---------------------------------------------------------------------------
# PEFT zip
# ---------------------------------------------------------------------------


def _check_zip_members(zf: zipfile.ZipFile, max_bytes: int) -> None:
    infos = zf.infolist()
    names = [i.filename for i in infos]
    for i in infos:
        n = i.filename
        if i.is_dir() or n.startswith("/") or "\\" in n or ".." in n.split("/") or "/" in n:
            raise InvalidAdapter(
                message=f"Zip must hold exactly {PEFT_WEIGHTS} and {PEFT_CONFIG} at its top "
                f"level (no directories or paths; found {n!r})."
            )
    if len(set(names)) != len(names) or set(names) != PEFT_MEMBERS:
        raise InvalidAdapter(
            message=f"Zip must hold exactly {PEFT_WEIGHTS} and {PEFT_CONFIG} "
            f"(found {sorted(names)})."
        )
    if sum(i.file_size for i in infos) > max_bytes:
        raise PayloadTooLarge(
            message=f"Adapter expands beyond the {settings.adapter_max_upload_mb} MB limit"
        )


def _extract_member(zf: zipfile.ZipFile, name: str, dest: Path, max_bytes: int) -> None:
    """Copy one member to ``dest`` with a hard byte cap (the header sizes are untrusted)."""
    written = 0
    with zf.open(name) as src, dest.open("wb") as out:
        while chunk := src.read(_COPY_CHUNK):
            written += len(chunk)
            if written > max_bytes:
                raise PayloadTooLarge(
                    message=f"Adapter expands beyond the {settings.adapter_max_upload_mb} MB limit"
                )
            out.write(chunk)


def _check_safetensors(path: Path) -> None:
    """A safetensors file starts with a little-endian u64 N and an N-byte JSON header."""
    size = path.stat().st_size
    with path.open("rb") as f:
        raw = f.read(8)
        ok = len(raw) == 8
        if ok:
            (n,) = struct.unpack("<Q", raw)
            ok = 0 < n <= min(_SAFETENSORS_HEADER_MAX, size - 8)
        if ok:
            try:
                header = json.loads(f.read(n))
                ok = isinstance(header, dict)
            except ValueError:
                ok = False
    if not ok:
        raise InvalidAdapter(message=f"{PEFT_WEIGHTS} is not a valid safetensors file.")


def _check_peft_config(path: Path, entry: model_catalog.CatalogEntry) -> None:
    if path.stat().st_size > _CONFIG_MAX_BYTES:
        raise InvalidAdapter(message=f"{PEFT_CONFIG} must be a small JSON file (< 1 MB).")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("not an object")
    except ValueError as exc:
        raise InvalidAdapter(message=f"{PEFT_CONFIG} must be a JSON object.") from exc
    if cfg.get("peft_type") != "LORA":
        raise InvalidAdapter(
            message=f"{PEFT_CONFIG} peft_type must be 'LORA' (got {cfg.get('peft_type')!r})."
        )
    base = cfg.get("base_model_name_or_path")
    accepted = _accepted_bases(entry)
    if base not in accepted:
        raise InvalidAdapter(
            message=f"{PEFT_CONFIG} base_model_name_or_path must be one of {list(accepted)} "
            f"to match the project's base model '{entry.name}' (got {base!r})."
        )


def _store_peft(upload: Path, dest_dir: Path, entry: model_catalog.CatalogEntry) -> Path:
    if _read_magic(upload, 4) != _ZIP_MAGIC or not zipfile.is_zipfile(upload):
        raise InvalidAdapter(message="Not a zip file: expected a .zip of a PEFT LoRA adapter.")
    max_bytes = settings.adapter_max_upload_mb * 1024 * 1024
    peft_dir = dest_dir / PEFT_SUBDIR
    peft_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(upload) as zf:
            _check_zip_members(zf, max_bytes)
            for name in sorted(PEFT_MEMBERS):
                _extract_member(zf, name, peft_dir / name, max_bytes)
    except zipfile.BadZipFile as exc:
        raise InvalidAdapter(
            message="The zip is corrupt; re-create it.", internal_detail=repr(exc)
        ) from exc
    _check_safetensors(peft_dir / PEFT_WEIGHTS)
    _check_peft_config(peft_dir / PEFT_CONFIG, entry)
    return peft_dir


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def validate_and_store(
    upload: Path, filename: str, base_model: str, adapter_id: str
) -> StoredAdapter:
    """Validate ``upload`` (already on disk, size-capped) against the project's base and
    place it under ``adapters_dir/{adapter_id}/``. Blocking: call via ``asyncio.to_thread``.

    On any failure the adapter directory is removed and the typed error propagates."""
    fmt = format_for_filename(filename)
    entry = model_catalog.resolve(base_model)
    if entry is None:
        raise InvalidAdapter(
            message=f"The project's base model '{base_model}' is not in the catalog; "
            f"expected one of {model_catalog.allowed_names()}."
        )
    dest_dir = adapter_dir(adapter_id)
    try:
        size = upload.stat().st_size
        digest = sha256_of(upload)
        if fmt == AdapterFormat.gguf:
            validate_gguf(upload, entry)
            gguf_path = dest_dir / GGUF_FILENAME
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(upload), gguf_path)
            return StoredAdapter(fmt, entry.name, digest, size, None, gguf_path)
        peft_dir = _store_peft(upload, dest_dir, entry)
        upload.unlink(missing_ok=True)  # the extracted members are the stored artifact
        return StoredAdapter(fmt, entry.name, digest, size, peft_dir, None)
    except BaseException:
        remove_adapter_files(adapter_id)
        raise


# ---------------------------------------------------------------------------
# The adapter job (E4.4) — runs in the worker
# ---------------------------------------------------------------------------

ADAPTER_JOB_KIND = "adapter"
_FAIL_UNEXPECTED = "Adapter processing failed unexpectedly; see the worker log."


def read_eval_rows(path: Path) -> list[dict]:
    """The SFT rows of an eval set (``prompt``/``response``/optional ``system``)."""
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def probe_load(base_model: str, gguf_path: str) -> None:
    """Load base + LoRA through ``model_manager`` and generate one token.

    A wrong-shape adapter otherwise surfaces only when the endpoint loads it. Any failure to
    apply or run the LoRA is :class:`AdapterIncompatible`; a base that will not load on its
    own is the node's problem and stays :class:`ModelNotFound`."""
    from adapta.core.backends.llamacpp import LlamaCppBackend
    from adapta.core.inference import InferenceRequest, Message

    backend = LlamaCppBackend()
    await backend.prepare(base_model, None)  # raises ModelNotFound if the base itself is absent
    try:
        handle = await backend.prepare(base_model, gguf_path)
        await backend.generate(
            handle,
            InferenceRequest(
                messages=[Message(role="user", content="ping")],
                model_name=base_model,
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                max_tokens=1,
                stream=False,
                adapter_path=gguf_path,
            ),
        )
    except Exception as exc:  # noqa: BLE001 - any load/run failure means "does not fit this base"
        detail = exc.internal_detail if isinstance(exc, ModelNotFound) else repr(exc)
        raise AdapterIncompatible(
            message=f"The adapter could not be loaded on base model '{base_model}'; it was "
            "probably trained for a different base, rank or target modules.",
            internal_detail=f"probe failed for {gguf_path}: {detail}",
        ) from exc


async def process_adapter(adapter_id: str) -> None:
    """Drive one adapter ``uploaded -> processing -> passed | failed``.

    A failed gate is a normal outcome (status ``failed`` with both scores in ``eval_metrics``),
    not an exception; a typed error (conversion, probe, missing eval set) also ends ``failed``
    with its safe message as ``failure_reason``. Re-running an adapter already ``passed`` or
    ``failed`` is a no-op, so a requeued job is safe. Seconds per stage are logged."""
    from adapta.core import adapter_conversion
    from adapta.db.models import Adapter, AdapterStatus, Dataset
    from adapta.db.session import AsyncSessionLocal
    from adapta.services import eval_gate

    async with AsyncSessionLocal() as db:
        adapter = await db.get(Adapter, adapter_id)
        if adapter is None or adapter.status in (AdapterStatus.passed, AdapterStatus.failed):
            logger.info("Adapter job %s: nothing to do", adapter_id)
            return
        adapter.status = AdapterStatus.processing
        adapter.failure_reason = None
        await db.commit()  # visible to the API before the slow work starts

        async def fail(reason: str, metrics: Optional[dict] = None) -> None:
            adapter.status = AdapterStatus.failed
            adapter.failure_reason = reason[:1000]
            if metrics is not None:
                adapter.eval_metrics = metrics
            await db.commit()

        stages: dict[str, float] = {}
        try:
            entry = model_catalog.resolve(adapter.base_model)
            dataset = (
                await db.get(Dataset, adapter.eval_dataset_id) if adapter.eval_dataset_id else None
            )
            if entry is None:
                raise AdapterIncompatible(
                    message=f"Base model '{adapter.base_model}' is not in the catalog."
                )
            if dataset is None or not dataset.task:
                raise InvalidAdapter(
                    message="The adapter's eval dataset is gone or has no task; upload the "
                    "adapter again with a valid eval dataset."
                )

            t = time.perf_counter()
            if adapter.format == AdapterFormat.peft:
                gguf = await adapter_conversion.convert_peft_to_gguf(
                    Path(adapter.peft_dir or ""), base_config_dir=entry.hf_config_dir()
                )
                adapter.gguf_path = str(gguf)
                await db.commit()
            stages["convert"] = time.perf_counter() - t
            gguf_path = adapter.gguf_path or ""

            t = time.perf_counter()
            await probe_load(entry.name, gguf_path)
            stages["probe"] = time.perf_counter() - t

            t = time.perf_counter()
            rows = await asyncio.to_thread(read_eval_rows, Path(dataset.storage_path))
            metrics = await eval_gate.evaluate(entry.name, gguf_path, rows, dataset.task)
            stages["score"] = time.perf_counter() - t
        except DomainError as exc:
            logger.error("Adapter %s failed: %s", adapter_id, exc.internal_detail or exc.message)
            await fail(exc.message)
            return
        except Exception:
            logger.exception("Adapter %s crashed", adapter_id)
            await fail(_FAIL_UNEXPECTED)
            return

        adapter.eval_metrics = metrics
        if metrics["passed"]:
            adapter.status = AdapterStatus.passed
            await db.commit()
        else:
            await fail(
                f"The adapter scored {metrics['adapter_score']:.3f} against the base model's "
                f"{metrics['base_score']:.3f} on {metrics['n_rows']} rows; it needs "
                f"+{metrics['min_improvement']:.2f} over the base or >= "
                f"{metrics['absolute_floor']:.2f} without regressing.",
                metrics,
            )
        logger.info(
            "Adapter %s -> %s (adapter %.3f, base %.3f); seconds per stage: %s",
            adapter_id,
            adapter.status.value,
            metrics["adapter_score"],
            metrics["base_score"],
            {k: round(v, 1) for k, v in stages.items()},
        )
