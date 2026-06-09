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
import uuid
from pathlib import Path

from brain.config import settings
from brain.core.gpu import torch_cuda_status
from brain.services.adapters import get_adapter_registry
from brain.services.jobs import get_job_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("brain.worker")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Shutdown signal received, finishing current job then stopping.")
    _shutdown = True


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

    logger.info("Starting job %s (project=%s, model=%s)", job_id, project_id, base_model)
    await queue.update_status(job_id, status="running", progress=0.0)

    # GPU guard: QLoRA requires torch to be usable on CUDA. Gate strictly on the
    # torch-level check (not the nvidia-smi heuristic) so a CPU-only host — or a
    # CUDA worker started without GPU pass-through — fails fast with a clear reason.
    cuda = torch_cuda_status()
    if not cuda.usable:
        err = f"GPU required for LoRA training — {cuda.reason}"
        logger.error(err)
        await queue.update_status(job_id, status="failed", error=err)
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

    trainer = LoRATrainer()
    success = await trainer.train(
        job_id=job_id,
        base_model=base_model,
        dataset_path=dataset_path,
        output_dir=output_dir,
        adapter_path=output_dir,
        config=config,
        progress_callback=lambda pct, msg="": asyncio.ensure_future(progress(pct, msg)),
    )

    if not success:
        await queue.update_status(job_id, status="failed", error="Training returned failure")
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
        eval_score = getattr(result, "score", 0.0)
        eval_passed = eval_score >= settings.eval_score_threshold
        logger.info("Eval score: %.4f (threshold=%.4f)", eval_score, settings.eval_score_threshold)
    except Exception as exc:
        logger.warning("Evaluation failed: %s", exc)

    if not eval_passed:
        await queue.update_status(
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
        await queue.update_status(job_id, status="failed", error=str(exc))
        return

    await queue.update_status(
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
    logger.info("Worker connected to Redis, waiting for jobs...")

    while not _shutdown:
        try:
            meta = await queue.dequeue(timeout=5)
            if meta is None:
                continue
            try:
                await _run_job(meta)
            except Exception as exc:
                job_id = meta.get("payload", meta).get("job_id", "unknown")
                logger.exception("Unhandled error in job %s: %s", job_id, exc)
                await queue.update_status(job_id, status="failed", error=str(exc))
        except Exception as exc:
            logger.exception("Worker loop error: %s", exc)
            await asyncio.sleep(2)

    await queue.close()
    logger.info("Worker stopped.")


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
