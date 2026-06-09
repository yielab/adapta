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


async def _set_status(queue, job_id: str, **fields) -> None:
    """Write a job's status to BOTH Redis (live progress) and Postgres (the source
    of truth the API + endpoint gate read). Persisting must never crash the job."""
    await queue.update_status(job_id, **fields)
    try:
        await update_job_record(job_id, **fields)
    except Exception:
        logger.exception("Failed to persist job %s status to Postgres", job_id)


async def _run_job(meta: dict) -> None:
    payload = meta.get("payload", meta)
    job_id = payload["job_id"]
    project_id = payload["project_id"]
    dataset_path = Path(payload["dataset_path"])
    base_model = payload["base_model"]
    training_config_raw = payload.get("training_config", {})

    queue = get_job_queue()

    async def progress(pct: float, log_line: str = "") -> None:
        await queue.update_status(job_id, status="running", progress=pct, logs=log_line)
        await queue.heartbeat()  # keep liveness fresh during long training steps

    logger.info("Starting job %s (project=%s, model=%s)", job_id, project_id, base_model)
    await _set_status(queue, job_id, status="running", progress=0.0)

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
    )

    # The trainer expects {"messages": [...]} format; our schema uses {"prompt":..., "response":...}.
    # Convert to a temporary messages-format file the trainer can consume.
    import json as _json
    converted_path = output_dir / "dataset_converted.jsonl"
    with dataset_path.open() as _src, converted_path.open("w") as _dst:
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
            _dst.write(_json.dumps({"messages": messages}) + "\n")
    dataset_path = converted_path

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
        base_model=base_model,
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
    eval_score = 0.0
    eval_passed = False
    try:
        from brain.training.evaluator import evaluator
        result = await evaluator.evaluate_adapter(
            job_id=job_id,
            agent_id=project_id,
            adapter_name=adapter_id,
            adapter_path=output_dir,
            dataset_path=dataset_path,
            base_model=base_model,
        )
        eval_score = result.score
        eval_passed = eval_score >= settings.eval_score_threshold
        logger.info("Eval score: %.4f (threshold=%.4f)", eval_score, settings.eval_score_threshold)
    except Exception as exc:
        logger.warning("Evaluation failed: %s", exc)

    if not eval_passed:
        await _set_status(
            queue,
            job_id,
            status="failed",
            eval_score=eval_score,
            eval_passed=False,
            error=f"Eval score {eval_score:.3f} below threshold {settings.eval_score_threshold:.3f}",
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
        )
    except Exception as exc:
        await _set_status(queue, job_id, status="failed", error=str(exc))
        return

    await _set_status(
        queue,
        job_id,
        status="succeeded",
        progress=1.0,
        adapter_path=str(output_dir),
        eval_score=eval_score,
        eval_passed=True,
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
    queue = get_job_queue()
    await queue.connect()

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
