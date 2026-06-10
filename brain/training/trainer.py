"""LoRA Training Engine"""

import asyncio
import json
import logging
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class LoRATrainer:
    """
    LoRA training engine for fine-tuning language models.

    This implementation uses:
    - HuggingFace Transformers for model loading
    - PEFT (Parameter-Efficient Fine-Tuning) for LoRA
    - TRL (Transformer Reinforcement Learning) for training
    - BitsAndBytes for 4-bit quantization (QLoRA)
    """

    def __init__(self):
        self.training_active = False
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if training dependencies are installed"""
        try:
            import datasets  # noqa: F401
            import peft  # noqa: F401
            import torch  # noqa: F401
            import transformers  # noqa: F401
            self.dependencies_available = True
            logger.info("Training dependencies available")
        except ImportError as e:
            self.dependencies_available = False
            logger.warning(
                f"Training dependencies not available: {e}\n"
                "Install with: pip install torch transformers peft datasets trl bitsandbytes accelerate"
            )

    async def train(
        self,
        job_id: str,
        base_model: str,
        dataset_path: Path,
        output_dir: Path,
        adapter_path: Path,
        config: "TrainingConfig",  # noqa: F821
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Train a LoRA adapter.

        Args:
            job_id: Unique job identifier
            base_model: Name or path of base model
            dataset_path: Path to training dataset (JSONL)
            output_dir: Directory for training outputs
            adapter_path: Directory to save final adapter
            config: Training configuration
            progress_callback: Callback for progress updates

        Returns:
            True if training completed successfully
        """
        if not self.dependencies_available:
            raise RuntimeError(
                "Training dependencies not installed. "
                "Run: pip install torch transformers peft datasets trl bitsandbytes accelerate"
            )

        self.training_active = True

        try:
            # Import training libraries
            import torch
            from datasets import load_dataset
            from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                DataCollatorForLanguageModeling,
                Trainer,
                TrainingArguments,
                set_seed,
            )

            # Determinism (A4.7): seed python/numpy/torch before any randomness so the
            # run is reproducible given the recorded seed + dataset hash + lib versions.
            set_seed(config.seed)

            logger.info(f"Starting training for job {job_id}")

            # Load tokenizer
            logger.info(f"Loading tokenizer for {base_model}")
            tokenizer = AutoTokenizer.from_pretrained(base_model)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            # Load dataset
            logger.info(f"Loading dataset from {dataset_path}")
            dataset = load_dataset("json", data_files=str(dataset_path))

            # Preprocess dataset
            def preprocess_function(examples):
                """Convert messages to text format"""
                texts = []
                for messages in examples["messages"]:
                    # Format as conversation
                    text = ""
                    for msg in messages:
                        role = msg["role"]
                        content = msg["content"]
                        if role == "system":
                            text += f"System: {content}\n"
                        elif role == "user":
                            text += f"User: {content}\n"
                        elif role == "assistant":
                            text += f"Assistant: {content}\n"
                    texts.append(text)

                # Tokenize
                return tokenizer(
                    texts,
                    truncation=True,
                    max_length=config.max_seq_length,
                    padding="max_length",
                )

            logger.info("Preprocessing dataset")
            tokenized_dataset = dataset.map(
                preprocess_function,
                batched=True,
                remove_columns=dataset["train"].column_names,
            )

            # Load model
            logger.info(f"Loading model {base_model}")

            if config.use_qlora:
                # Load with 4-bit quantization
                from transformers import BitsAndBytesConfig

                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                )

                model = AutoModelForCausalLM.from_pretrained(
                    base_model,
                    quantization_config=bnb_config,
                    device_map="auto",
                    trust_remote_code=True,
                )
                model = prepare_model_for_kbit_training(model)
            else:
                # Load normally
                model = AutoModelForCausalLM.from_pretrained(
                    base_model,
                    device_map="auto",
                    torch_dtype=torch.float16,
                    trust_remote_code=True,
                )

            # Configure LoRA
            logger.info("Configuring LoRA")
            lora_config = LoraConfig(
                r=config.lora_r,
                lora_alpha=config.lora_alpha,
                target_modules=config.target_modules,
                lora_dropout=config.lora_dropout,
                bias="none",
                task_type="CAUSAL_LM",
            )

            # Apply LoRA to model
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()

            # Training arguments
            training_args = TrainingArguments(
                output_dir=str(output_dir),
                num_train_epochs=config.num_epochs,
                per_device_train_batch_size=config.batch_size,
                gradient_accumulation_steps=config.gradient_accumulation_steps,
                learning_rate=config.learning_rate,
                warmup_steps=config.warmup_steps,
                logging_steps=config.logging_steps,
                save_steps=config.save_steps,
                eval_steps=config.eval_steps if "validation" in tokenized_dataset else None,
                save_total_limit=3,
                fp16=True,
                gradient_checkpointing=config.gradient_checkpointing,
                optim=config.optimizer,
                weight_decay=config.weight_decay,
                max_grad_norm=config.max_grad_norm,
                report_to="none",  # Disable wandb/tensorboard
                remove_unused_columns=False,
            )

            # Custom callback for progress updates
            from transformers import TrainerCallback

            class ProgressCallback(TrainerCallback):
                def __init__(self, callback_fn, job_id):
                    self.callback_fn = callback_fn
                    self.job_id = job_id

                def on_log(self, args, state, control, logs=None, **kwargs):
                    if logs and self.callback_fn:
                        # Extract metrics
                        step = state.global_step
                        epoch = state.epoch
                        loss = logs.get("loss", 0.0)
                        lr = logs.get("learning_rate", 0.0)

                        # Call progress callback
                        asyncio.create_task(
                            self.callback_fn(
                                job_id=self.job_id,
                                step=step,
                                epoch=epoch,
                                loss=loss,
                                learning_rate=lr,
                            )
                        )

            # Causal-LM loss needs `labels`. The preprocessor emits only input_ids/
            # attention_mask, so without a collator the model returns logits with no
            # loss ("The model did not return a loss"). DataCollatorForLanguageModeling
            # (mlm=False) derives labels from input_ids and masks pad positions to -100.
            data_collator = DataCollatorForLanguageModeling(tokenizer, mlm=False)

            # Create trainer
            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=tokenized_dataset["train"],
                eval_dataset=tokenized_dataset.get("validation"),
                data_collator=data_collator,
                callbacks=[ProgressCallback(progress_callback, job_id)] if progress_callback else [],
            )

            # Start training
            logger.info("Starting training loop")
            trainer.train()

            # Save final adapter
            logger.info(f"Saving adapter to {adapter_path}")
            trainer.model.save_pretrained(str(adapter_path))
            tokenizer.save_pretrained(str(adapter_path))

            # Save our training metadata to a SEPARATE file. Do NOT touch
            # adapter_config.json — PEFT's save_pretrained already wrote it with the
            # `peft_type`/target_modules PeftModel.from_pretrained() needs; overwriting
            # it with this dict stripped `peft_type` and broke adapter loading at eval.
            # Provenance (A4.7): seed + dataset hash + library versions so this
            # adapter can be reproduced/audited months later. dataset_path is the
            # exact train split the worker wrote.
            from brain.training.provenance import build_provenance

            training_metadata = {
                "base_model": base_model,
                "lora_r": config.lora_r,
                "lora_alpha": config.lora_alpha,
                "lora_dropout": config.lora_dropout,
                "target_modules": config.target_modules,
                "trained_at": time.time(),
                "job_id": job_id,
                "provenance": build_provenance(base_model, dataset_path, config.seed),
            }

            with open(adapter_path / "training_metadata.json", "w") as f:
                json.dump(training_metadata, f, indent=2)

            logger.info(f"Training completed for job {job_id}")
            self.training_active = False
            return True

        except Exception as e:
            logger.error(f"Training failed for job {job_id}: {e}")
            logger.error(traceback.format_exc())
            self.training_active = False
            raise

    def stop_training(self):
        """Stop active training (graceful interruption)"""
        self.training_active = False
        logger.info("Training stop requested")


# Global trainer instance
trainer = LoRATrainer()
