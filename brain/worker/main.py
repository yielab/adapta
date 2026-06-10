"""
Training worker — consumes jobs from the Redis queue and runs QLoRA training.
Run as a separate process/container:
    python -m brain.worker.main

Requires the [training] optional dependencies (torch, peft, trl, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import uuid
from pathlib import Path

from brain.config import settings
from brain.core.gpu import torch_cuda_status
from brain.core.logging_config import configure_logging
from brain.services.adapters import get_adapter_registry
from brain.services.jobs import get_job_queue
from brain.services.training import update_job_record

configure_logging()
logger = logging.getLogger("brain.worker")


async def _set_status(queue, job_id: str, *, critical: bool = False, **fields) -> None:
    """Write a job's status to BOTH Redis (live progress) and Postgres (the source
    of truth the API + endpoint gate read).

    Normally a failed Postgres write is logged but swallowed (a metering blip must
    not crash a job). The initial ``running`` transition passes ``critical=True``
    (A4.2): if it can't be persisted, the job must NOT train untracked — crash
    recovery scans Postgres for ``running`` rows, and a job stuck at ``queued``
    there (while it actually ran) would be invisible to it. On failure we re-raise
    so the worker loop requeues the job instead."""
    await queue.update_status(job_id, **fields)
    try:
        await update_job_record(job_id, **fields)
    except Exception:
        logger.exception("Failed to persist job %s status to Postgres", job_id)
        if critical:
            raise


async def _run_job(meta: dict) -> None:
    payload = meta.get("payload", meta)
    job_id = payload["job_id"]
    project_id = payload["project_id"]
    dataset_path = Path(payload["dataset_path"])
    base_model = payload["base_model"]
    training_config_raw = payload.get("training_config", {})

    # Resolve the operator-facing catalog name to the HF repo id the trainer/evaluator
    # load via from_pretrained() (A3.3). Serving (model_manager) resolves the GGUF from
    # the SAME catalog entry, so train and serve can never reference different bases.
    from brain.core.model_catalog import resolve_hf_id

    hf_base_model = resolve_hf_id(base_model)

    queue = get_job_queue()

    async def progress(pct: float, log_line: str = "") -> None:
        await queue.update_status(job_id, status="running", progress=pct, logs=log_line)
        await queue.heartbeat()  # keep liveness fresh during long training steps

    logger.info("Starting job %s (project=%s, model=%s)", job_id, project_id, base_model)
    # Critical: the `running` transition MUST land in Postgres before training, or a
    # crash would leave it invisible to recovery (A4.2). On failure this raises and
    # the worker loop requeues the job.
    await _set_status(queue, job_id, status="running", progress=0.0, critical=True)

    # GPU guard: QLoRA requires torch to be usable on CUDA. Gate strictly on the
    # torch-level check (not the nvidia-smi heuristic) so a CPU-only host — or a
    # CUDA worker started without GPU pass-through — fails fast with a clear reason.
    cuda = torch_cuda_status()
    if not cuda.usable:
        err = f"GPU required for LoRA training — {cuda.reason}"
        logger.error(err)
        await _set_status(queue, job_id, status="failed", error=err)
        return

    adapter_id = str(uuid.uuid4())
    output_dir = settings.adapters_dir / adapter_id
    output_dir.mkdir(parents=True, exist_ok=True)

    from brain.training.models import TrainingConfig
    from brain.training.trainer import LoRATrainer

    # Build config from payload; fill defaults.
    # TrainingConfig only holds hyperparameters — base_model/output_dir go to train().
    tc_raw = training_config_raw if isinstance(training_config_raw, dict) else {}
    config = TrainingConfig(
        num_epochs=tc_raw.get("num_epochs", 3),
        batch_size=tc_raw.get("batch_size", 4),
        learning_rate=tc_raw.get("learning_rate", 2e-4),
        lora_r=tc_raw.get("lora_r", 16),
        lora_alpha=tc_raw.get("lora_alpha", 32),
        lora_dropout=tc_raw.get("lora_dropout", 0.1),
        max_seq_length=tc_raw.get("max_seq_length", 512),
        seed=tc_raw.get("seed", 42),  # recorded into provenance (A4.7)
    )

    # The trainer expects {"messages": [...]} format; our schema uses {"prompt":..., "response":...}.
    # Convert to messages format, then SPLIT into a train file and a HELD-OUT eval file.
    # The eval gate must measure generalization, so the model is scored on rows it never
    # trained on (A3.2): we hold out the last ~20% of rows (see models.split_holdout) and
    # train only on the remainder. This is the single place the split is decided so the
    # train/eval files can never overlap.
    import json as _json

    from brain.training.models import split_holdout

    rows = []
    with dataset_path.open() as _src:
        for line in _src:
            line = line.strip()
            if not line:
                continue
            obj = _json.loads(line)
            messages = [
                {"role": "user", "content": obj["prompt"]},
                {"role": "assistant", "content": obj["response"]},
            ]
            if obj.get("system"):
                messages.insert(0, {"role": "system", "content": obj["system"]})
            rows.append({"messages": messages})

    n_holdout = split_holdout(len(rows))
    if n_holdout > 0:
        train_rows = rows[:-n_holdout]
        eval_rows = rows[-n_holdout:]
    else:
        # Degenerate (<=1 row) dataset: nothing to hold out. Train and eval on what we
        # have; the absolute eval-score floor still applies.
        train_rows = rows
        eval_rows = rows

    train_path = output_dir / "dataset_train.jsonl"
    eval_path = output_dir / "dataset_eval.jsonl"
    with train_path.open("w") as _dst:
        for r in train_rows:
            _dst.write(_json.dumps(r) + "\n")
    with eval_path.open("w") as _dst:
        for r in eval_rows:
            _dst.write(_json.dumps(r) + "\n")
    logger.info(
        "Dataset split: %d train rows, %d held-out eval rows", len(train_rows), len(eval_rows)
    )
    dataset_path = train_path

    # The trainer's ProgressCallback invokes this per log-step with keyword args
    # (job_id, step, epoch, loss, learning_rate) and wraps the returned coroutine in
    # a task — so it must be an async fn with that exact signature (a `lambda pct,msg`
    # raised TypeError and killed training). Map epoch→a 10–90% band; eval/registration
    # fill the last 10%.
    async def _on_train_log(job_id=None, step=0, epoch=0.0, loss=0.0, learning_rate=0.0, **_):
        frac = (epoch / config.num_epochs) if config.num_epochs else 0.0
        await progress(min(0.9, 0.1 + 0.8 * frac), f"epoch {epoch:.2f} step {step} loss {loss:.4f}")

    trainer = LoRATrainer()
    success = await trainer.train(
        job_id=job_id,
        base_model=hf_base_model,
        dataset_path=dataset_path,
        output_dir=output_dir,
        adapter_path=output_dir,
        config=config,
        progress_callback=_on_train_log,
    )

    if not success:
        await _set_status(queue, job_id, status="failed", error="Training returned failure")
        return

    # Evaluate adapter
    await progress(0.95, "Running evaluation...")
    try:
        from brain.training.evaluator import evaluator
        # Score on the HELD-OUT split (eval_path), never the rows we trained on.
        result = await evaluator.evaluate_adapter(
            job_id=job_id,
            agent_id=project_id,
            adapter_name=adapter_id,
            adapter_path=output_dir,
            dataset_path=eval_path,
            base_model=hf_base_model,
        )
    except Exception as exc:
        # An evaluator CRASH is not a gate verdict (A4.6). Reporting it as
        # "score below threshold" would mislead the operator into thinking the
        # adapter is bad when really the eval step itself broke. Fail distinctly.
        logger.exception("Evaluation crashed for job %s", job_id)
        await _set_status(queue, job_id, status="failed", error=f"Evaluation failed: {exc}")
        return

    eval_score = result.score
    eval_passed = eval_score >= settings.eval_score_threshold
    # Persist the FULL eval result (score, base_score, delta, held_out, samples,
    # metrics) so the gate verdict is auditable, not just a scalar (A4.6).
    eval_metrics_json = _json.dumps(result.to_dict())
    if result.base_score is not None:
        logger.info(
            "Eval score: %.4f (threshold=%.4f) | base=%.4f delta=%+.4f (held-out, response-only)",
            eval_score, settings.eval_score_threshold, result.base_score, result.score_delta,
        )
    else:
        logger.info(
            "Eval score: %.4f (threshold=%.4f) (held-out, response-only)",
            eval_score, settings.eval_score_threshold,
        )

    if not eval_passed:
        await _set_status(
            queue,
            job_id,
            status="failed",
            eval_score=eval_score,
            eval_passed=False,
            eval_metrics=eval_metrics_json,
            error=f"Eval score {eval_score:.3f} below threshold {settings.eval_score_threshold:.3f}",
        )
        return

    # Convert the PEFT adapter to a GGUF LoRA so the llama-cpp serving runtime can
    # actually apply it (A3.1). This is the step that makes train->eval->serve real:
    # without it the endpoint silently serves the base model. Done here (post-eval,
    # in the worker) because the converter toolchain lives only in the worker image.
    await progress(0.97, "Converting adapter for serving (GGUF LoRA)...")
    adapter_gguf_path = None
    try:
        from brain.core.adapter_conversion import convert_peft_to_gguf
        gguf_path = await convert_peft_to_gguf(output_dir, base_model_id=hf_base_model)
        adapter_gguf_path = str(gguf_path)
    except Exception as exc:
        # A converted, servable adapter is the whole point of a fine-tune endpoint.
        # If conversion fails, do NOT register/succeed — surface it so the endpoint
        # gate keeps serving blocked rather than silently falling back to base.
        logger.exception("Adapter GGUF conversion failed for job %s", job_id)
        await _set_status(
            queue, job_id, status="failed",
            eval_score=eval_score, eval_passed=eval_passed,
            error=f"Adapter conversion for serving failed: {exc}",
        )
        return

    # Register adapter
    try:
        registry = get_adapter_registry()
        registry.register(
            adapter_id=adapter_id,
            project_id=project_id,
            job_id=job_id,
            adapter_path=str(output_dir),
            eval_score=eval_score,
            base_model=base_model,
            adapter_gguf_path=adapter_gguf_path,
        )
    except Exception as exc:
        await _set_status(queue, job_id, status="failed", error=str(exc))
        return

    # Persist the SERVABLE artifact (the GGUF LoRA) as the job's adapter_path: the
    # endpoint copies this onto Endpoint.adapter_path, and serving loads it directly
    # via llama-cpp's lora_path. The PEFT directory remains in the registry under
    # `path` for re-conversion / audit.
    await _set_status(
        queue,
        job_id,
        status="succeeded",
        progress=1.0,
        adapter_path=adapter_gguf_path,
        eval_score=eval_score,
        eval_passed=True,
        eval_metrics=eval_metrics_json,
    )
    logger.info("Job %s complete — adapter %s registered", job_id, adapter_id)


def _log_gpu_banner() -> None:
    """Log torch/CUDA readiness once at startup so operators see GPU state in logs."""
    cuda = torch_cuda_status()
    if cuda.usable:
        logger.info(
            "GPU ready: %s | torch %s (CUDA %s)",
            cuda.device_name, cuda.torch_version, cuda.cuda_version,
        )
    else:
        logger.warning(
            "No usable training GPU: %s | torch %s (CUDA build: %s). "
            "Jobs will be rejected with 'GPU required'.",
            cuda.reason, cuda.torch_version, cuda.cuda_version,
        )


async def worker_loop() -> None:
    _log_gpu_banner()
    settings.ensure_dirs()  # adapters/datasets dirs must exist before any job runs
    queue = get_job_queue()
    await queue.connect()

    # Reconcile jobs a previous worker left behind (crashed mid-training, or a lost
    # enqueue) before consuming new work (A4.2). A recovery failure must not stop the
    # worker from serving the live queue, so it's best-effort.
    try:
        from brain.services.training import recover_orphaned_jobs
        await recover_orphaned_jobs()
    except Exception:
        logger.exception("Crash-recovery reconciliation failed (continuing to serve queue)")

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()
    in_flight: dict = {"task": None}

    def _request_shutdown(signame: str) -> None:
        logger.info("%s received — stopping; any in-flight job will be requeued.", signame)
        shutdown.set()
        task = in_flight["task"]
        if task is not None and not task.done():
            task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_shutdown, sig.name)

    logger.info("Worker connected to Redis, waiting for jobs...")
    await queue.heartbeat()
    while not shutdown.is_set():
        await queue.heartbeat()
        try:
            meta = await queue.dequeue(timeout=5)
        except Exception as exc:
            logger.exception("Worker loop error: %s", exc)
            await asyncio.sleep(2)
            continue
        if meta is None:
            continue

        job_id = meta.get("payload", meta).get("job_id", "unknown")
        task = asyncio.ensure_future(_run_job(meta))
        in_flight["task"] = task
        try:
            await task
        except asyncio.CancelledError:
            # Graceful shutdown mid-job: return it to the queue so it isn't lost.
            logger.warning("Job %s interrupted by shutdown — requeuing.", job_id)
            await queue.requeue(job_id)
            break
        except Exception as exc:
            logger.exception("Unhandled error in job %s: %s", job_id, exc)
            await _set_status(queue, job_id, status="failed", error=str(exc))
        finally:
            in_flight["task"] = None

    await queue.close()
    logger.info("Worker stopped.")


async def _healthcheck() -> int:
    """Return 0 if a worker heartbeat is fresh in Redis, 1 otherwise.

    Used by the container healthcheck so a silently dead/hung worker (which still
    looks `Up` to Docker) is reported unhealthy.
    """
    queue = get_job_queue()
    await queue.connect()
    try:
        return 0 if await queue.worker_alive() else 1
    finally:
        await queue.close()


def main() -> None:
    if "--healthcheck" in sys.argv:
        raise SystemExit(asyncio.run(_healthcheck()))
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
