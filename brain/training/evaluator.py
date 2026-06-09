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
    ) -> EvaluationResult:
        """
        Evaluate a trained adapter on a validation dataset.

        Args:
            job_id: Training job ID
            agent_id: Agent ID
            adapter_name: Name of the adapter
            adapter_path: Path to the adapter directory
            base_model: Base model name
            dataset_path: Path to validation dataset (JSONL)
            num_samples: Number of sample predictions to save
            max_examples: Maximum examples to evaluate (None = all)

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
            model = AutoModelForCausalLM.from_pretrained(
                base_model,
                device_map="auto",
                torch_dtype=torch.float16,
                trust_remote_code=True,
            )

            # Load adapter
            logger.info(f"Loading adapter from {adapter_path}")
            model = PeftModel.from_pretrained(model, str(adapter_path))
            model.eval()

            # Load validation dataset
            logger.info(f"Loading validation dataset from {dataset_path}")
            dataset = load_dataset("json", data_files=str(dataset_path))
            eval_data = dataset["train"]

            # Limit dataset if specified
            if max_examples:
                eval_data = eval_data.select(range(min(max_examples, len(eval_data))))

            num_examples = len(eval_data)
            logger.info(f"Evaluating on {num_examples} examples")

            # Prepare for evaluation
            total_loss = 0.0
            total_tokens = 0
            correct_tokens = 0  # noqa: F841
            sample_predictions = []

            # Evaluate each example
            with torch.no_grad():
                for idx, example in enumerate(eval_data):
                    messages = example["messages"]

                    # Format as conversation
                    text = ""
                    target_text = ""
                    for msg in messages:
                        role = msg["role"]
                        content = msg["content"]
                        if role == "system":
                            text += f"System: {content}\n"
                        elif role == "user":
                            text += f"User: {content}\n"
                        elif role == "assistant":
                            text += f"Assistant: {content}\n"
                            target_text = content

                    # Tokenize
                    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=2048)
                    inputs = {k: v.to(model.device) for k, v in inputs.items()}

                    # Get loss
                    outputs = model(**inputs, labels=inputs["input_ids"])
                    loss = outputs.loss.item()
                    total_loss += loss

                    # Count tokens
                    num_tokens = inputs["input_ids"].shape[1]
                    total_tokens += num_tokens

                    # Generate prediction for sample
                    if idx < num_samples:
                        # Create input without assistant response
                        input_text = text.replace(f"Assistant: {target_text}\n", "Assistant: ")
                        input_ids = tokenizer(input_text, return_tensors="pt", truncation=True, max_length=2048)
                        input_ids = {k: v.to(model.device) for k, v in input_ids.items()}

                        # Generate
                        with torch.no_grad():
                            generated_ids = model.generate(
                                **input_ids,
                                max_new_tokens=256,
                                temperature=0.7,
                                do_sample=True,
                                pad_token_id=tokenizer.pad_token_id,
                            )

                        # Decode prediction
                        prediction = tokenizer.decode(
                            generated_ids[0][input_ids["input_ids"].shape[1]:],
                            skip_special_tokens=True,
                        )

                        sample_predictions.append({
                            "input": input_text,
                            "expected": target_text,
                            "predicted": prediction,
                        })

                    if (idx + 1) % 10 == 0:
                        logger.info(f"Evaluated {idx + 1}/{num_examples} examples")

            # Calculate metrics
            avg_loss = total_loss / num_examples
            perplexity = math.exp(avg_loss) if avg_loss < 100 else float('inf')
            # Intrinsic LM score the eval gate tests (1/perplexity, clamped to [0,1]).
            score = score_from_loss(avg_loss)

            metrics = EvaluationMetrics(
                loss=avg_loss,
                perplexity=perplexity,
                accuracy=None,  # Would require specific task definition
                exact_match=None,
                token_accuracy=None,
                bleu_score=None,
                coherence_score=None,
                fluency_score=None,
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
                sample_predictions=sample_predictions,
                created_at=start_time,
                duration_seconds=duration,
            )

            logger.info(
                f"Evaluation {eval_id} completed: "
                f"loss={avg_loss:.4f}, perplexity={perplexity:.2f}, score={score:.4f}, "
                f"duration={duration:.1f}s"
            )

            return result

        except Exception as e:
            logger.error(f"Evaluation {eval_id} failed: {e}")
            raise


# Global evaluator instance
evaluator = ModelEvaluator()
