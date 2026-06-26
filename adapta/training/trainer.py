"""LoRA Training Engine"""

import asyncio
import gc
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
                callbacks=(
                    [ProgressCallback(progress_callback, job_id)] if progress_callback else []
                ),
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
            from adapta.training.provenance import build_provenance

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

    async def train_vision(
        self,
        job_id: str,
        base_model: str,
        dataset_path: Path,
        bundle_dir: Path,
        output_dir: Path,
        adapter_path: Path,
        config: "TrainingConfig",  # noqa: F821
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """Train a LoRA adapter on a VLM (image+text → text) — §V3.2.

        Constraints proven by the V0.3 spike and enforced here:
        - **Vision tower frozen; LoRA on the language model's attention
          projections only** (anchored regex) — required for the GGUF-LoRA
          conversion to work. Asserted after wrapping, not assumed.
        - **Response-only loss**: every token up to and including the final
          assistant header (which includes the image placeholder tokens) is
          masked to -100, matching the eval gate's semantics.
        - Rows are the schema's {prompt, response, system?, images[1]} with
          image paths resolved against ``bundle_dir``.
        - Effective batching is gradient accumulation over ``config.batch_size``
          rows (VLM rows have heterogeneous image-token counts; padding them
          into true batches buys little at this scale).
        """
        if not self.dependencies_available:
            raise RuntimeError("Training dependencies not installed.")

        self.training_active = True
        try:
            import torch
            from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
            from PIL import Image
            from transformers import (
                AutoProcessor,
                BitsAndBytesConfig,
                Qwen2_5_VLForConditionalGeneration,
                set_seed,
            )

            set_seed(config.seed)
            logger.info("Starting VISION training for job %s (base=%s)", job_id, base_model)

            # min/max_pixels bound the vision-token count per image so a high-res
            # photo can't blow past VRAM; the validator already capped raw size.
            processor = AutoProcessor.from_pretrained(
                base_model, min_pixels=256 * 28 * 28, max_pixels=512 * 28 * 28
            )

            bnb = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            # v1 supports the one pinned VLM architecture (catalog: qwen2.5-vl-3b).
            # A new arch extends this dispatch — and must re-prove V0.3's conversion.
            model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                base_model, quantization_config=bnb, device_map="auto"
            )
            model = prepare_model_for_kbit_training(model)

            lora_config = LoraConfig(
                r=config.lora_r,
                lora_alpha=config.lora_alpha,
                lora_dropout=config.lora_dropout,
                bias="none",
                task_type="CAUSAL_LM",
                # Anchored to the language model's layer path so no vision-tower
                # module is ever wrapped (GGUF-LoRA conversion constraint, V0.3).
                target_modules=r".*language_model\.layers\.\d+\.self_attn\.(q_proj|k_proj|v_proj|o_proj)",
            )
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()
            offenders = [
                n
                for n, p in model.named_parameters()
                if p.requires_grad and "language_model" not in n and "lm_head" not in n
            ]
            if offenders:
                raise RuntimeError(
                    f"LoRA touched non-LM modules (conversion would fail): {offenders[:5]}"
                )

            rows = []
            with Path(dataset_path).open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))

            marker = processor.tokenizer.encode("<|im_start|>assistant\n", add_special_tokens=False)

            def _encode(row: dict):
                img = Image.open(bundle_dir / row["images"][0]).convert("RGB")
                messages = []
                if row.get("system"):
                    messages.append(
                        {"role": "system", "content": [{"type": "text", "text": row["system"]}]}
                    )
                messages.append(
                    {
                        "role": "user",
                        "content": [{"type": "image"}, {"type": "text", "text": row["prompt"]}],
                    }
                )
                messages.append(
                    {"role": "assistant", "content": [{"type": "text", "text": row["response"]}]}
                )
                text = processor.apply_chat_template(messages, tokenize=False)
                inputs = processor(text=[text], images=[img], return_tensors="pt")
                labels = inputs["input_ids"].clone()
                ids = inputs["input_ids"][0].tolist()
                start = None
                for i in range(len(ids) - len(marker), -1, -1):
                    if ids[i : i + len(marker)] == marker:
                        start = i + len(marker)
                        break
                if start is None:
                    raise RuntimeError("assistant marker not found in templated row")
                labels[0, :start] = -100  # prompt + image tokens are context, not target
                inputs["labels"] = labels
                return inputs

            accum = max(1, config.batch_size)
            opt = torch.optim.AdamW(
                (p for p in model.parameters() if p.requires_grad), lr=config.learning_rate
            )
            model.train()
            step = 0
            for epoch in range(config.num_epochs):
                total = 0.0
                opt.zero_grad()
                for n, row in enumerate(rows, 1):
                    inputs = _encode(row).to(model.device)
                    out = model(**inputs)
                    (out.loss / accum).backward()
                    if n % accum == 0 or n == len(rows):
                        opt.step()
                        opt.zero_grad()
                    total += out.loss.item()
                    step += 1
                avg = total / max(1, len(rows))
                logger.info("[vision] epoch %d/%d avg_loss=%.4f", epoch + 1, config.num_epochs, avg)
                if progress_callback:
                    # Awaited directly (unlike the HF-Trainer text path) so Redis
                    # progress + the worker heartbeat actually run between epochs.
                    await progress_callback(
                        job_id=job_id,
                        step=step,
                        epoch=float(epoch + 1),
                        loss=avg,
                        learning_rate=config.learning_rate,
                    )

            logger.info("Saving vision adapter to %s", adapter_path)
            model.save_pretrained(str(adapter_path))
            processor.tokenizer.save_pretrained(str(adapter_path))
            processor.save_pretrained(str(adapter_path))

            # Conversion needs the RAW hub config (flat keys): transformers 5.x's
            # AutoConfig re-nests it into text_config, which the converter's hub
            # loader can't read (V0.3 caveat 1). Stage it beside the adapter so
            # convert_peft_to_gguf can pass a local --base dir.
            from huggingface_hub import hf_hub_download

            base_cfg_dir = adapter_path / "base_config"
            base_cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg_file = hf_hub_download(base_model, "config.json")
            (base_cfg_dir / "config.json").write_bytes(Path(cfg_file).read_bytes())

            from adapta.training.provenance import build_provenance

            training_metadata = {
                "base_model": base_model,
                "modality": "vision",
                "lora_r": config.lora_r,
                "lora_alpha": config.lora_alpha,
                "lora_dropout": config.lora_dropout,
                "target_modules": lora_config.target_modules,
                "trained_at": time.time(),
                "job_id": job_id,
                # bundle_dir folds referenced image bytes into the hash (§V2.3).
                "provenance": build_provenance(
                    base_model, dataset_path, config.seed, bundle_dir=bundle_dir
                ),
            }
            with open(adapter_path / "training_metadata.json", "w") as f:
                json.dump(training_metadata, f, indent=2, default=str)

            # Free the training model BEFORE eval loads its own copy — a 3B VLM
            # twice does not fit an 8 GB card. PeftModel↔base is a reference
            # cycle, so without an explicit collect the CUDA tensors stay
            # allocated and empty_cache() releases nothing.
            del model
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            logger.info("Vision training completed for job %s", job_id)
            self.training_active = False
            return True

        except Exception as e:
            logger.error(f"Vision training failed for job {job_id}: {e}")
            logger.error(traceback.format_exc())
            self.training_active = False
            raise

    async def train_dpo(
        self,
        job_id: str,
        base_model: str,
        dataset_path: Path,
        output_dir: Path,
        adapter_path: Path,
        config: "TrainingConfig",  # noqa: F821
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """Train a LoRA adapter using Direct Preference Optimisation (DPO, D4).

        Dataset rows must have the shape ``{prompt, chosen, rejected}`` as produced
        by the worker's DPO row-conversion step. The same QLoRA + LoRA setup as SFT
        is used; only the trainer and loss objective change (TRL DPOTrainer, β-scaled
        KL penalty).

        The resulting PEFT adapter artifact is identical to an SFT adapter — it flows
        through the same eval-gate → convert → serve pipeline unchanged.
        """
        if not self.dependencies_available:
            raise RuntimeError(
                "Training dependencies not installed. "
                "Run: pip install torch transformers peft datasets trl bitsandbytes accelerate"
            )

        self.training_active = True

        try:
            import torch
            from datasets import load_dataset
            from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                set_seed,
            )
            from trl import DPOConfig, DPOTrainer

            set_seed(config.seed)

            logger.info("Starting DPO training for job %s (β=%.3f)", job_id, config.dpo_beta)

            tokenizer = AutoTokenizer.from_pretrained(base_model)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            raw_dataset = load_dataset("json", data_files=str(dataset_path))

            # DPO dataset columns: prompt, chosen, rejected (plain strings — TRL
            # templates them internally via the chat template if one exists).
            # Keep only the three required columns; extras (system, metadata) are dropped.
            def _keep_dpo_cols(examples):
                return {
                    "prompt": examples["prompt"],
                    "chosen": examples["chosen"],
                    "rejected": examples["rejected"],
                }

            dpo_dataset = raw_dataset.map(
                _keep_dpo_cols,
                batched=True,
                remove_columns=[
                    c for c in raw_dataset["train"].column_names
                    if c not in ("prompt", "chosen", "rejected")
                ],
            )

            if config.use_qlora:
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
                model = AutoModelForCausalLM.from_pretrained(
                    base_model,
                    device_map="auto",
                    torch_dtype=torch.float16,
                    trust_remote_code=True,
                )

            lora_config = LoraConfig(
                r=config.lora_r,
                lora_alpha=config.lora_alpha,
                target_modules=config.target_modules,
                lora_dropout=config.lora_dropout,
                bias="none",
                task_type="CAUSAL_LM",
            )
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()

            from transformers import TrainerCallback

            class ProgressCallback(TrainerCallback):
                def __init__(self, callback_fn, job_id):
                    self.callback_fn = callback_fn
                    self.job_id = job_id

                def on_log(self, args, state, control, logs=None, **kwargs):
                    if logs and self.callback_fn:
                        asyncio.create_task(
                            self.callback_fn(
                                job_id=self.job_id,
                                step=state.global_step,
                                epoch=state.epoch,
                                loss=logs.get("loss", 0.0),
                                learning_rate=logs.get("learning_rate", 0.0),
                            )
                        )

            dpo_args = DPOConfig(
                output_dir=str(output_dir),
                num_train_epochs=config.num_epochs,
                per_device_train_batch_size=config.batch_size,
                gradient_accumulation_steps=config.gradient_accumulation_steps,
                learning_rate=config.learning_rate,
                warmup_steps=config.warmup_steps,
                logging_steps=config.logging_steps,
                save_steps=config.save_steps,
                fp16=True,
                gradient_checkpointing=config.gradient_checkpointing,
                optim=config.optimizer,
                weight_decay=config.weight_decay,
                max_grad_norm=config.max_grad_norm,
                report_to="none",
                beta=config.dpo_beta,
                max_length=config.max_seq_length,
                max_prompt_length=config.max_seq_length // 2,
            )

            dpo_trainer = DPOTrainer(
                model=model,
                args=dpo_args,
                train_dataset=dpo_dataset["train"],
                tokenizer=tokenizer,
                callbacks=(
                    [ProgressCallback(progress_callback, job_id)] if progress_callback else []
                ),
            )

            logger.info("Starting DPO training loop")
            dpo_trainer.train()

            logger.info("Saving DPO adapter to %s", adapter_path)
            dpo_trainer.model.save_pretrained(str(adapter_path))
            tokenizer.save_pretrained(str(adapter_path))

            from adapta.training.provenance import build_provenance

            training_metadata = {
                "base_model": base_model,
                "method": "dpo",
                "dpo_beta": config.dpo_beta,
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

            logger.info("DPO training completed for job %s", job_id)
            self.training_active = False
            return True

        except Exception as e:
            logger.error("DPO training failed for job %s: %s", job_id, e)
            logger.error(traceback.format_exc())
            self.training_active = False
            raise

    def stop_training(self):
        """Stop active training (graceful interruption)"""
        self.training_active = False
        logger.info("Training stop requested")


# Global trainer instance
trainer = LoRATrainer()
