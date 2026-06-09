"""Model Evaluation Engine"""

import logging
import math
import time
import uuid
from pathlib import Path
from typing import Optional

from .models import EvaluationMetrics, EvaluationResult, score_from_loss

logger = logging.getLogger(__name__)


class ModelEvaluator:
    """
    Model evaluation engine for testing trained adapters.

    Supports:
    - Perplexity calculation
    - Loss computation
    - Token accuracy
    - Sample predictions for inspection
    """

    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if evaluation dependencies are installed"""
        try:
            import datasets  # noqa: F401
            import peft  # noqa: F401
            import torch  # noqa: F401
            import transformers  # noqa: F401
            self.dependencies_available = True
            logger.info("Evaluation dependencies available")
        except ImportError as e:
            self.dependencies_available = False
            logger.warning(
                f"Evaluation dependencies not available: {e}\n"
                "Install with: pip install torch transformers peft datasets"
            )

    @staticmethod
    def _render_prompt_and_target(messages: list) -> tuple[str, str]:
        """Render a chat row into (prompt_text, target_response).

        ``prompt_text`` is everything up to and including the ``Assistant: `` cue but
        WITHOUT the answer (what the model is conditioned on); ``target_response`` is the
        assistant's content. Mirrors the trainer's plain ``Role: content`` formatting so
        the masking boundary is consistent with how the model was trained.
        """
        prompt_text = ""
        target_text = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt_text += f"System: {content}\n"
            elif role == "user":
                prompt_text += f"User: {content}\n"
            elif role == "assistant":
                target_text = content
        prompt_text += "Assistant: "
        return prompt_text, target_text

    def _tokenize_with_response_mask(self, tokenizer, messages: list):
        """Tokenize one row into (input_ids, labels) where labels mask the prompt.

        Loss must be computed on the **response tokens only**: prompt tokens get label
        ``-100`` (ignored by HF's cross-entropy), so the score reflects the model's
        ability to produce the target answer, not to model the operator's prompt text.
        Returns CPU tensors of shape (1, T); the caller moves them to the device.
        """
        prompt_text, target_text = self._render_prompt_and_target(messages)
        full_text = prompt_text + target_text

        prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        full = tokenizer(
            full_text, return_tensors="pt", truncation=True, max_length=2048,
            add_special_tokens=False,
        )
        input_ids = full["input_ids"]
        labels = input_ids.clone()
        # Mask the prompt span (and any tokens beyond the truncation point handled by
        # clamping). Everything in [0, len(prompt_ids)) is prompt → ignore.
        mask_len = min(len(prompt_ids), labels.shape[1])
        labels[0, :mask_len] = -100
        return {"input_ids": input_ids, "labels": labels}

    @staticmethod
    def _response_only_loss(model, tokenized: list, device) -> float:
        """Mean per-row response-only cross-entropy over a pre-tokenized split.

        Each row already carries prompt-masked labels (-100). Rows whose response was
        fully truncated away (no unmasked label) are skipped. Returns +inf if no row
        has a scorable response.
        """
        total_loss = 0.0
        counted = 0
        for row in tokenized:
            labels = row["labels"]
            if int((labels != -100).sum().item()) == 0:
                continue  # nothing to score (response truncated out)
            input_ids = row["input_ids"].to(device)
            labels = labels.to(device)
            out = model(input_ids=input_ids, labels=labels)
            loss = out.loss.item()
            if loss == loss:  # not NaN
                total_loss += loss
                counted += 1
        if counted == 0:
            return float("inf")
        return total_loss / counted

    async def evaluate_adapter(
        self,
        job_id: str,
        agent_id: str,
        adapter_name: str,
        adapter_path: Path,
        base_model: str,
        dataset_path: Path,
        num_samples: int = 5,
        max_examples: Optional[int] = None,
        compare_base: bool = True,
    ) -> EvaluationResult:
        """
        Evaluate a trained adapter on a HELD-OUT validation dataset.

        The caller MUST pass a ``dataset_path`` that the model did **not** train on
        (the worker holds out the last fraction of rows for this — see
        ``brain.training.models.split_holdout``). Scoring on training rows measures
        memorization, not the generalization the eval gate is meant to guard.

        The reported loss is **response-only** (prompt tokens masked with -100), so it
        reflects how well the model produces the target answer rather than how well it
        models the operator's prompt text. When ``compare_base`` is set, the same split
        is also scored on the un-adapted base model and the adapter-vs-base delta is
        reported (the gate still uses the adapter's absolute score).

        Args:
            job_id: Training job ID
            agent_id: Agent ID
            adapter_name: Name of the adapter
            adapter_path: Path to the adapter directory
            base_model: Base model name
            dataset_path: Path to the HELD-OUT validation dataset (JSONL)
            num_samples: Number of sample predictions to save
            max_examples: Maximum examples to evaluate (None = all)
            compare_base: Also score the base model on the same split for a delta

        Returns:
            EvaluationResult with metrics and sample predictions
        """
        if not self.dependencies_available:
            raise RuntimeError(
                "Evaluation dependencies not installed. "
                "Run: pip install torch transformers peft datasets"
            )

        start_time = time.time()
        eval_id = str(uuid.uuid4())

        logger.info(f"Starting evaluation {eval_id} for adapter {adapter_name}")

        try:
            # Import libraries
            import torch
            from datasets import load_dataset
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # Load tokenizer
            logger.info(f"Loading tokenizer from {adapter_path}")
            tokenizer = AutoTokenizer.from_pretrained(str(adapter_path))
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            # Load base model
            logger.info(f"Loading base model {base_model}")
            base = AutoModelForCausalLM.from_pretrained(
                base_model,
                device_map="auto",
                torch_dtype=torch.float16,
                trust_remote_code=True,
            )

            # Load adapter ON TOP of the base. PeftModel wraps `base`; with the adapter
            # disabled it behaves as the base model, which lets us score base-vs-adapter
            # on the SAME loaded weights (no second base load) — see disable_adapter().
            logger.info(f"Loading adapter from {adapter_path}")
            model = PeftModel.from_pretrained(base, str(adapter_path))
            model.eval()

            # Load validation dataset (the HELD-OUT split the worker wrote).
            logger.info(f"Loading held-out validation dataset from {dataset_path}")
            dataset = load_dataset("json", data_files=str(dataset_path))
            eval_data = dataset["train"]

            # Limit dataset if specified
            if max_examples:
                eval_data = eval_data.select(range(min(max_examples, len(eval_data))))

            num_examples = len(eval_data)
            logger.info(f"Evaluating on {num_examples} held-out examples")

            # Pre-tokenize the split once: (input_ids, response-masked labels). We reuse
            # the exact same tensors for the adapter pass and the base pass so the delta
            # is apples-to-apples.
            tokenized = [
                self._tokenize_with_response_mask(tokenizer, example["messages"])
                for example in eval_data
            ]

            # --- Adapter (the fine-tune) on the held-out split, response-only loss ---
            with torch.no_grad():
                adapter_loss = self._response_only_loss(model, tokenized, model.device)

            # --- Base model on the SAME split (adapter disabled) for a relative signal ---
            base_loss: Optional[float] = None
            if compare_base:
                try:
                    with torch.no_grad(), model.disable_adapter():
                        base_loss = self._response_only_loss(model, tokenized, model.device)
                except Exception as exc:  # base comparison is best-effort, never blocks
                    logger.warning("Base-model comparison failed: %s", exc)

            # --- Sample predictions for human inspection (held-out prompts) ---
            sample_predictions = []
            with torch.no_grad():
                for idx, example in enumerate(eval_data):
                    if idx >= num_samples:
                        break
                    prompt_text, target_text = self._render_prompt_and_target(example["messages"])
                    input_ids = tokenizer(prompt_text, return_tensors="pt", truncation=True, max_length=2048)
                    input_ids = {k: v.to(model.device) for k, v in input_ids.items()}
                    generated_ids = model.generate(
                        **input_ids,
                        max_new_tokens=256,
                        temperature=0.7,
                        do_sample=True,
                        pad_token_id=tokenizer.pad_token_id,
                    )
                    prediction = tokenizer.decode(
                        generated_ids[0][input_ids["input_ids"].shape[1]:],
                        skip_special_tokens=True,
                    )
                    sample_predictions.append({
                        "input": prompt_text,
                        "expected": target_text,
                        "predicted": prediction,
                    })

            # Calculate metrics — score is built from the RESPONSE-ONLY held-out loss.
            perplexity = math.exp(adapter_loss) if adapter_loss < 100 else float("inf")
            score = score_from_loss(adapter_loss)

            base_perplexity = None
            base_score = None
            score_delta = None
            loss_improvement = None
            if base_loss is not None:
                base_perplexity = math.exp(base_loss) if base_loss < 100 else float("inf")
                base_score = score_from_loss(base_loss)
                score_delta = score - base_score
                loss_improvement = base_loss - adapter_loss

            metrics = EvaluationMetrics(
                loss=adapter_loss,
                perplexity=perplexity,
                accuracy=None,  # Would require specific task definition
                exact_match=None,
                token_accuracy=None,
                bleu_score=None,
                coherence_score=None,
                fluency_score=None,
                base_loss=base_loss,
                base_perplexity=base_perplexity,
                loss_improvement=loss_improvement,
            )

            duration = time.time() - start_time

            result = EvaluationResult(
                eval_id=eval_id,
                job_id=job_id,
                agent_id=agent_id,
                adapter_name=adapter_name,
                adapter_path=str(adapter_path),
                dataset_path=str(dataset_path),
                num_examples=num_examples,
                metrics=metrics,
                score=score,
                base_score=base_score,
                score_delta=score_delta,
                held_out=True,
                sample_predictions=sample_predictions,
                created_at=start_time,
                duration_seconds=duration,
            )

            logger.info(
                "Evaluation %s completed (held-out, response-only): "
                "loss=%.4f ppl=%.2f score=%.4f%s duration=%.1fs",
                eval_id, adapter_loss, perplexity, score,
                (f" | base_score={base_score:.4f} delta={score_delta:+.4f}"
                 if base_score is not None else ""),
                duration,
            )

            return result

        except Exception as e:
            logger.error(f"Evaluation {eval_id} failed: {e}")
            raise


# Global evaluator instance
evaluator = ModelEvaluator()
