"""
Training coordination service.
Handles dataset validation and job enqueuing; actual training runs in the worker.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from adapta.config import settings
from adapta.db.models import Dataset, DatasetStatus, JobStatus, TrainingJob
from adapta.domain.errors import InvalidRequest, NotFound
from adapta.services.jobs import get_job_queue

logger = logging.getLogger(__name__)

DATASET_SCHEMA_PATH = Path("specs/schemas/training_dataset.schema.json")

# §V2: image formats accepted inside a dataset bundle.
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class BundleError(ValueError):
    """A dataset .zip bundle that cannot be safely extracted (zip-slip, caps,
    disallowed content). The message is operator-safe."""


def _load_schema() -> Optional[dict]:
    if DATASET_SCHEMA_PATH.exists():
        return json.loads(DATASET_SCHEMA_PATH.read_text())  # type: ignore[no-any-return]
    return None


def extract_bundle(zip_path: Path, dest_dir: Path) -> Path:
    """Safely extract a dataset bundle (§V2.1) and return the manifest path.

    A bundle is a .zip holding exactly one ``*.jsonl`` manifest at its root and
    the images the manifest references (``ALLOWED_IMAGE_EXTENSIONS``). Hostile
    archives are rejected before any byte is written: path traversal (zip-slip),
    absolute paths, symlinks, over-cap file counts / uncompressed size, and
    disallowed file types all raise :class:`BundleError`.
    """
    import zipfile

    if not zipfile.is_zipfile(zip_path):
        raise BundleError("Not a valid .zip archive")

    max_bytes = settings.max_bundle_uncompressed_mb * 1024 * 1024
    dest_dir = dest_dir.resolve()

    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if len(members) > settings.max_bundle_files:
            raise BundleError(
                f"Bundle has {len(members)} files; at most {settings.max_bundle_files} are allowed"
            )
        total = sum(m.file_size for m in members)
        if total > max_bytes:
            raise BundleError(
                f"Bundle uncompressed size ({total // (1024 * 1024)} MB) exceeds the "
                f"{settings.max_bundle_uncompressed_mb} MB limit"
            )

        manifests: list[str] = []
        for m in members:
            name = m.filename
            # Zip-slip / absolute-path / drive-letter protection: the resolved
            # destination must stay inside dest_dir.
            if (
                name.startswith(("/", "\\"))
                or ".." in Path(name).parts
                or ":" in name.split("/")[0]
            ):
                raise BundleError(f"Unsafe path in bundle: {name!r}")
            resolved = (dest_dir / name).resolve()
            if not resolved.is_relative_to(dest_dir):
                raise BundleError(f"Unsafe path in bundle: {name!r}")
            # Symlink entries (external_attr high bits = S_IFLNK) would let a
            # later member write through the link — reject outright.
            if (m.external_attr >> 16) & 0o170000 == 0o120000:
                raise BundleError(f"Symlinks are not allowed in bundles: {name!r}")
            ext = Path(name).suffix.lower()
            if ext == ".jsonl":
                if "/" in name:
                    raise BundleError("The .jsonl manifest must be at the bundle root")
                manifests.append(name)
            elif ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise BundleError(
                    f"Disallowed file type in bundle: {name!r} (allowed: one root .jsonl + "
                    + "/".join(sorted(e.lstrip(".") for e in ALLOWED_IMAGE_EXTENSIONS))
                    + ")"
                )

        if len(manifests) != 1:
            raise BundleError(
                f"Bundle must contain exactly one root .jsonl manifest (found {len(manifests)})"
            )

        # Extract member-by-member with a HARD cap on actual bytes written. The earlier
        # ``sum(m.file_size)`` pre-check trusts the zip's central directory, which an
        # attacker controls — a "zip bomb" can declare a small uncompressed size yet
        # decompress to gigabytes. Streaming each entry and aborting once the real total
        # crosses the cap is what actually bounds disk use.
        dest_dir.mkdir(parents=True, exist_ok=True)
        written = 0
        for m in members:
            target = (dest_dir / m.filename).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, target.open("wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise BundleError(
                            "Bundle decompresses beyond the "
                            f"{settings.max_bundle_uncompressed_mb} MB limit"
                        )
                    out.write(chunk)

    return dest_dir / manifests[0]


def _validate_image(bundle_dir: Path, rel_path: str) -> Optional[str]:
    """Validate one referenced image; returns an error string or None."""
    from PIL import Image

    candidate = (bundle_dir / rel_path).resolve()
    if not candidate.is_relative_to(bundle_dir.resolve()):
        return f"image path {rel_path!r} escapes the bundle"
    if not candidate.is_file():
        return f"image {rel_path!r} not found in the bundle"
    if candidate.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        return f"image {rel_path!r} has a disallowed format"
    if candidate.stat().st_size > settings.max_image_mb * 1024 * 1024:
        return f"image {rel_path!r} exceeds the {settings.max_image_mb} MB limit"
    try:
        with Image.open(candidate) as img:
            img.verify()  # decodability without loading full pixel data
        with Image.open(candidate) as img:  # verify() exhausts the fp — reopen for size
            w, h = img.size
        if max(w, h) > settings.max_image_side_px:
            return (
                f"image {rel_path!r} is {w}x{h}; the longest side may be at most "
                f"{settings.max_image_side_px}px"
            )
    except Exception:
        return f"image {rel_path!r} cannot be decoded"
    return None


# How many row/image problems to list before truncating the report. A large
# bundle (hundreds of invoices) with a systemic mistake could otherwise produce a
# multi-megabyte error string; the operator only needs a representative batch to
# fix the pattern, so we cap and tell them how many more there were.
MAX_REPORTED_ERRORS = 25


def _detect_row_method(obj: dict) -> str:
    """Return 'dpo' if the row has chosen/rejected fields, 'sft' otherwise."""
    return "dpo" if ("chosen" in obj or "rejected" in obj) else "sft"


def _validate_row(
    i: int, obj: dict, schema: Optional[dict], bundle_dir: Optional[Path]
) -> tuple[list[str], int, str]:
    """Validate one parsed row; return (errors, num_images_counted, detected_method).

    Collects *all* problems on the row (it does not stop at the first) so the
    caller can build one report covering the whole file. Accepts both SFT rows
    (prompt + response) and DPO preference rows (prompt + chosen + rejected).
    """
    errors: list[str] = []
    detected = _detect_row_method(obj)

    if not isinstance(obj.get("prompt"), str) or not obj["prompt"].strip():
        errors.append(f"Line {i}: missing or empty 'prompt' field")

    if detected == "dpo":
        if not isinstance(obj.get("chosen"), str) or not obj["chosen"].strip():
            errors.append(f"Line {i}: DPO row missing or empty 'chosen' field")
        if not isinstance(obj.get("rejected"), str) or not obj["rejected"].strip():
            errors.append(f"Line {i}: DPO row missing or empty 'rejected' field")
    else:
        if not isinstance(obj.get("response"), str) or not obj["response"].strip():
            errors.append(f"Line {i}: missing or empty 'response' field")

        images = obj.get("images") or []
        if images and bundle_dir is None:
            errors.append(
                f"Line {i}: rows with 'images' must be uploaded as a .zip bundle "
                "(one root .jsonl manifest + the image files), not a plain .jsonl."
            )

    if schema:
        import jsonschema

        try:
            jsonschema.validate(obj, schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Line {i}: schema violation — {e.message}")

    counted = 0
    if detected == "sft":
        images = obj.get("images") or []
        if images and bundle_dir is not None:
            for rel in images:
                img_err = _validate_image(bundle_dir, rel)
                if img_err:
                    errors.append(f"Line {i}: {img_err}")
                else:
                    counted += 1
    return errors, counted, detected


def _format_error_report(errors: list[str]) -> str:
    """Build one operator-facing message from collected per-row problems."""
    shown = errors[:MAX_REPORTED_ERRORS]
    body = "\n".join(f"  • {e}" for e in shown)
    header = f"Found {len(errors)} problem(s) in the dataset:"
    if len(errors) > MAX_REPORTED_ERRORS:
        body += f"\n  … and {len(errors) - MAX_REPORTED_ERRORS} more"
    return f"{header}\n{body}\nFix these and re-upload."


def validate_dataset(
    path: Path, bundle_dir: Optional[Path] = None
) -> tuple[bool, Optional[str], int, int]:
    """Validate a JSONL file against the training dataset schema.

    Returns (is_valid, error_message, num_samples, num_images).

    Accepts both SFT rows (prompt + response) and DPO preference rows
    (prompt + chosen + rejected). Rows within a single dataset must all be
    the same type — mixing SFT and DPO rows is rejected.

    Validation does **not** stop at the first bad row: it scans the whole file
    and reports up to :data:`MAX_REPORTED_ERRORS` problems at once, so an
    operator fixing a large bundle sees every issue in one pass instead of
    discovering them one re-upload at a time.
    """
    try:
        schema = _load_schema()
        num_samples = 0
        num_images = 0
        errors: list[str] = []
        detected_methods: set[str] = set()
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"Line {i}: invalid JSON — {exc}")
                    if len(errors) >= MAX_REPORTED_ERRORS:
                        break
                    continue

                row_errors, counted, row_method = _validate_row(i, obj, schema, bundle_dir)
                detected_methods.add(row_method)
                if row_errors:
                    errors.extend(row_errors)
                    if len(errors) >= MAX_REPORTED_ERRORS:
                        break
                    continue

                num_samples += 1
                num_images += counted

        if len(detected_methods) > 1:
            errors.append(
                "Dataset mixes SFT rows (prompt/response) and DPO rows "
                "(prompt/chosen/rejected) — a dataset must be one type only."
            )

        if errors:
            return False, _format_error_report(errors), 0, 0
        if num_samples == 0:
            return False, "Dataset is empty — must have at least one row", 0, 0

        return True, None, num_samples, num_images

    except Exception as exc:
        return False, str(exc), 0, 0


async def update_job_record(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    logs: Optional[str] = None,
    adapter_path: Optional[str] = None,
    eval_score: Optional[float] = None,
    eval_passed: Optional[bool] = None,
    eval_metrics: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Persist a training job's lifecycle to Postgres (the source of truth the API
    and the endpoint-creation gate read).

    The Redis ``JobQueue.update_status`` only updates live progress; without this the
    Postgres row stayed at ``queued`` forever, so a finished job never looked terminal
    to ``GET /jobs/{id}`` and a passed adapter could never bind an endpoint.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from adapta.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(select(TrainingJob).where(TrainingJob.id == job_id))
        ).scalar_one_or_none()
        if row is None:
            logger.error("update_job_record: job %s not found — cannot persist status", job_id)
            return
        if status is not None:
            row.status = JobStatus(status)
            if status == "running" and row.started_at is None:
                row.started_at = datetime.now(timezone.utc)
            if status in ("succeeded", "failed", "cancelled"):
                row.finished_at = datetime.now(timezone.utc)
        if progress is not None:
            row.progress = progress
        if logs is not None:
            row.logs = logs
        if adapter_path is not None:
            row.adapter_path = adapter_path
        if eval_score is not None:
            row.eval_score = eval_score
        if eval_passed is not None:
            row.eval_passed = eval_passed
        if eval_metrics is not None:
            row.eval_metrics = eval_metrics
        if error is not None:
            row.error_message = error
        await db.commit()


# Safe bounds for operator-supplied training hyperparameters (A4.12). Outside
# these a run would OOM, diverge, or never finish — reject at enqueue, not after
# a GPU has been tied up. (min, max), inclusive.
_HYPERPARAM_BOUNDS: dict = {
    "num_epochs": (1, 100),
    "batch_size": (1, 128),
    "learning_rate": (1e-6, 1e-1),
    "lora_r": (1, 256),
    "lora_alpha": (1, 512),
    "lora_dropout": (0.0, 0.9),
    "max_seq_length": (16, 8192),
    "dpo_beta": (0.0, 1.0),
}


def validate_training_config(training_config: Optional[dict]) -> None:
    """Reject out-of-range hyperparameters before a job is enqueued (A4.12)."""
    if not training_config:
        return
    for key, (lo, hi) in _HYPERPARAM_BOUNDS.items():
        if key not in training_config or training_config[key] is None:
            continue
        val = training_config[key]
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise InvalidRequest(message=f"training_config.{key} must be a number")
        if not (lo <= val <= hi):
            raise InvalidRequest(
                message=f"training_config.{key}={val} is out of range — must be between {lo} and {hi}."
            )


def check_min_training_samples(num_samples: Optional[int]) -> None:
    """Reject a too-small dataset before a job is created (A4.6).

    Below ``settings.min_training_samples`` the held-out eval split collapses
    (e.g. 1 row → 0 held out → the gate scores the training rows), so the eval
    gate would only measure memorization. Raising here keeps that signal honest.
    """
    n = num_samples or 0
    if n < settings.min_training_samples:
        raise InvalidRequest(
            message=(
                f"Dataset has {n} sample(s); at least {settings.min_training_samples} "
                "are required to train. A smaller set can't be split into a held-out "
                "eval set, so the gate would only measure memorization."
            )
        )


async def recover_orphaned_jobs(max_attempts: int = 1) -> tuple[int, int]:
    """Reconcile jobs a crashed worker left behind (A4.2). Returns (requeued, failed).

    A hard crash (OOM-kill, power loss, segfault) pops a job off the Redis queue
    but never drives it to a terminal state — so it sits ``running`` in Postgres
    forever with no live worker. A failed enqueue (or a wiped Redis) can likewise
    leave a job ``queued`` in Postgres but absent from the queue. On worker startup
    we find both and either requeue them (reconstructing the payload from Postgres,
    so it survives a wiped Redis) or fail them once they've burned their retries.

    Single-worker assumption: at startup no other worker is live, so any ``running``
    job is orphaned. Run this before the dequeue loop.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from adapta.db.models import JobStatus as _JobStatus
    from adapta.db.models import Project, TrainingJob
    from adapta.db.session import AsyncSessionLocal

    queue = get_job_queue()
    queued_ids = set(await queue.queued_job_ids())
    requeued = failed = 0

    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(TrainingJob).where(
                        TrainingJob.status.in_([_JobStatus.running, _JobStatus.queued])
                    )
                )
            )
            .scalars()
            .all()
        )

        for row in rows:
            # A `queued` job that's still in the Redis queue is legitimately waiting.
            if row.status == _JobStatus.queued and row.id in queued_ids:
                continue

            is_crash = row.status == _JobStatus.running
            if is_crash:
                # Only a real crash (was `running`) consumes a retry; a lost-enqueue
                # `queued` job never actually ran.
                row.attempts = (row.attempts or 0) + 1

            dataset = (
                await db.execute(select(Dataset).where(Dataset.id == row.dataset_id))
            ).scalar_one_or_none()
            project = (
                await db.execute(select(Project).where(Project.id == row.project_id))
            ).scalar_one_or_none()

            give_up = (
                (is_crash and row.attempts > max_attempts) or dataset is None or project is None
            )
            if give_up:
                reason = (
                    "dataset or project no longer exists"
                    if dataset is None or project is None
                    else f"worker crashed during training and exhausted retries ({max_attempts})"
                )
                row.status = _JobStatus.failed
                row.error_message = f"Job could not be recovered — {reason}."
                row.finished_at = datetime.now(timezone.utc)
                await db.commit()
                await queue.update_status(row.id, status="failed", error=row.error_message)
                failed += 1
                logger.warning("Orphaned job %s failed during recovery — %s", row.id, reason)
                continue

            assert dataset is not None and project is not None  # give_up covered None
            row.status = _JobStatus.queued
            row.progress = 0.0
            await db.commit()

            payload = {
                "job_id": row.id,
                "project_id": row.project_id,
                "dataset_id": row.dataset_id,
                "dataset_path": dataset.storage_path,
                "base_model": project.base_model,
                "training_config": json.loads(row.training_config) if row.training_config else {},
            }
            await queue.enqueue(row.id, payload)
            requeued += 1
            logger.warning(
                "Requeued orphaned job %s (was %s, attempt %d)",
                row.id,
                "running" if is_crash else "queued-lost",
                row.attempts,
            )

    if requeued or failed:
        logger.info("Crash recovery: %d job(s) requeued, %d failed", requeued, failed)
    return requeued, failed


async def enqueue_training_job(
    db: AsyncSession,
    project_id: str,
    dataset_id: str,
    base_model: str,
    training_config: Optional[dict] = None,
    method: str = "sft",
) -> TrainingJob:
    """Create a TrainingJob record and push it to the Redis queue."""
    from sqlalchemy import select

    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
    )
    dataset: Optional[Dataset] = result.scalar_one_or_none()
    if not dataset:
        raise NotFound(message="Dataset not found")
    if dataset.status != DatasetStatus.valid:
        raise InvalidRequest(message="Dataset is not valid — cannot start training")
    # §V3: the dataset's modality must match the base model's. A vision dataset
    # on a text base would crash mid-train (no image inputs); a text dataset on
    # a vision base would waste the vision tower — reject both with the fix.
    from adapta.core.model_catalog import resolve as resolve_catalog

    entry = resolve_catalog(base_model)
    model_modality = entry.modality if entry else "text"
    if dataset.modality != model_modality:
        if dataset.modality == "vision":
            raise InvalidRequest(
                message=(
                    f"This dataset contains images but the project's base model "
                    f"{base_model!r} is text-only — create the project with a vision "
                    "base model (e.g. qwen2.5-vl-3b-instruct) to train on images."
                )
            )
        raise InvalidRequest(
            message=(
                f"The project's base model {base_model!r} is a vision model but this "
                "dataset has no images — upload an image bundle, or use a text base model."
            )
        )
    check_min_training_samples(dataset.num_samples)
    validate_training_config(training_config)

    # DPO is text-only: vision LoRA DPO is not supported (preference pairs with
    # image inputs require a separate evaluation protocol we don't implement yet).
    if method == "dpo" and dataset.modality != "text":
        raise InvalidRequest(
            message="DPO training is only supported for text datasets — use method=sft for vision."
        )

    job = TrainingJob(
        project_id=project_id,
        dataset_id=dataset_id,
        status=JobStatus.queued,
        training_config=json.dumps(training_config or {}),
    )
    db.add(job)
    await db.flush()

    payload = {
        "job_id": job.id,
        "project_id": project_id,
        "dataset_id": dataset_id,
        "dataset_path": dataset.storage_path,
        "base_model": base_model,
        "training_config": training_config or {},
        "method": method,
    }

    queue = get_job_queue()
    try:
        await queue.enqueue(job.id, payload)
    except RuntimeError as exc:
        raise InvalidRequest(
            message="Job queue is not available — training cannot be started right now.",
            internal_detail=str(exc),
        ) from exc
    logger.info("Training job %s enqueued for project %s", job.id, project_id)
    return job
