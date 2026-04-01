"""Fine-tuning pipeline for causal LM spam classification via LoRA.

Trains a causal language model (e.g. TinyLlama, Phi, Gemma) on
instruction-formatted spam/ham examples using LoRA adapters (PEFT).
The resulting model can be exported to GGUF for Ollama deployment.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Fallback instruction template when the tokenizer has no chat_template.
# Only used for models that lack ``apply_chat_template`` (rare).
_FALLBACK_TEMPLATE = (
    "<|system|>\n"
    "{system_prompt}\n"
    "<|user|>\n"
    "Classify this email:\n\n{text}\n"
    "<|assistant|>\n"
    "{response}"
)


def _get_system_prompt() -> str:
    """Return the shared spam classification system prompt."""
    from tobira.backends.prompts import SPAM_CLASSIFICATION_SYSTEM

    return SPAM_CLASSIFICATION_SYSTEM


def _import_deps() -> tuple:
    """Lazily import torch, transformers, and peft."""
    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
        )
    except ImportError as exc:
        raise ImportError(
            "torch and transformers are required for causal LM training. "
            "Install them with: pip install tobira[gguf]"
        ) from exc

    try:
        from peft import LoraConfig, get_peft_model
    except ImportError as exc:
        raise ImportError(
            "peft is required for LoRA fine-tuning. "
            "Install it with: pip install tobira[gguf]"
        ) from exc

    return torch, AutoModelForCausalLM, AutoTokenizer, LoraConfig, get_peft_model


@dataclass(frozen=True)
class CausalTrainingResult:
    """Result of a causal LM fine-tuning run.

    Attributes:
        model_name: Base model name used for fine-tuning.
        output_path: Path where the merged model was saved.
        num_samples: Number of training samples.
        epochs: Number of training epochs completed.
        final_loss: Average loss in the final epoch.
        gguf_path: Path to exported GGUF model, if export was performed.
    """

    model_name: str
    output_path: str
    num_samples: int
    epochs: int
    final_loss: float
    gguf_path: str | None = None


@dataclass
class CausalTrainingConfig:
    """Configuration for causal LM LoRA fine-tuning.

    Attributes:
        model_name: HuggingFace model name or path for a causal LM.
        epochs: Number of training epochs.
        batch_size: Training batch size.
        learning_rate: Peak learning rate for AdamW.
        max_length: Maximum token sequence length.
        device: Device string. When *None*, auto-selects.
        label_names: Ordered list of classification label names.
        seed: Random seed for reproducibility.
        lora_r: LoRA rank.
        lora_alpha: LoRA alpha (scaling factor).
        lora_dropout: LoRA dropout probability.
        lora_target_modules: Modules to apply LoRA to. When *None*,
            uses a sensible default for common architectures.
        eval_split: Fraction of data held out for evaluation.
    """

    model_name: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 2e-4
    max_length: int = 512
    device: str | None = None
    label_names: list[str] = field(default_factory=lambda: ["ham", "spam"])
    seed: int = 42
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_target_modules: list[str] | None = None
    eval_split: float = 0.1


def _format_example(text: str, label: str, tokenizer: Any = None) -> str:
    """Format a training example as an instruction string.

    When *tokenizer* is provided and has ``apply_chat_template``, it is
    used to produce the correct chat format for the specific model.
    Otherwise a generic fallback template is used.

    Args:
        text: Email text.
        label: Classification label ("spam" or "ham").
        tokenizer: Optional tokenizer with ``apply_chat_template``.

    Returns:
        Formatted instruction string.
    """
    system_prompt = _get_system_prompt()
    response = json.dumps({"label": label})

    if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Classify this email:\n\n{text}"},
                {"role": "assistant", "content": response},
            ]
            result: str = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
            return result
        except Exception:
            logger.debug("apply_chat_template failed, using fallback template")

    return _FALLBACK_TEMPLATE.format(
        system_prompt=system_prompt, text=text, response=response
    )


def _split_data(
    records: list[dict[str, str]],
    eval_split: float,
    seed: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split records into train and eval sets.

    Args:
        records: Full dataset.
        eval_split: Fraction for evaluation.
        seed: Random seed.

    Returns:
        Tuple of (train_records, eval_records).
    """
    import random

    rng = random.Random(seed)
    shuffled = list(records)
    rng.shuffle(shuffled)

    n_eval = int(len(shuffled) * eval_split)
    if n_eval >= len(shuffled):
        n_eval = 0
    elif eval_split > 0 and n_eval == 0 and len(shuffled) > 1:
        n_eval = 1

    if n_eval > 0:
        return shuffled[n_eval:], shuffled[:n_eval]
    return shuffled, []


def train_causal(
    data: list[dict[str, str]],
    output_path: str | Path,
    config: CausalTrainingConfig | None = None,
) -> CausalTrainingResult:
    """Fine-tune a causal LM for spam classification using LoRA.

    Trains a causal language model on instruction-formatted spam/ham
    examples using LoRA adapters, then merges the adapters back into
    the base model for a standalone deployment.

    Args:
        data: List of dicts with ``"text"`` and ``"label"`` keys.
        output_path: Directory to save the merged fine-tuned model.
        config: Training configuration. Uses defaults if None.

    Returns:
        CausalTrainingResult with training metadata.

    Raises:
        ValueError: If data is empty or labels are invalid.
        ImportError: If required packages are not installed.
    """
    if not data:
        raise ValueError("data must not be empty")

    if config is None:
        config = CausalTrainingConfig()

    # Validate labels before importing heavy dependencies
    label_set = set(config.label_names)
    data_labels = {d["label"] for d in data}
    unknown = data_labels - label_set
    if unknown:
        raise ValueError(
            f"Data contains unknown labels {unknown}. "
            f"Expected one of {config.label_names}"
        )

    (
        torch,
        AutoModelForCausalLM,
        AutoTokenizer,
        LoraConfig,
        get_peft_model,
    ) = _import_deps()

    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # Device selection
    if config.device is None:
        device_str = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device_str = config.device

    if device_str == "cpu":
        logger.warning(
            "Training causal LM on CPU. This will be very slow. "
            "Consider using a GPU."
        )

    device = torch.device(device_str)

    # Split data
    train_records, eval_records = _split_data(
        data, config.eval_split, config.seed
    )
    logger.info(
        "Data split: %d train, %d eval", len(train_records), len(eval_records)
    )

    # Load tokenizer and model
    logger.info("Loading causal LM: %s", config.model_name)
    tokenizer = AutoTokenizer.from_pretrained(config.model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        config.model_name,
        torch_dtype=torch.float32 if device_str == "cpu" else torch.float16,
    )

    # Apply LoRA
    target_modules = config.lora_target_modules
    if target_modules is None:
        target_modules = _detect_target_modules(model)

    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)
    model.to(device)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info(
        "LoRA: trainable=%d (%.2f%% of %d)",
        trainable,
        100.0 * trainable / total,
        total,
    )

    # Prepare training data
    train_texts = [
        _format_example(r["text"], r["label"], tokenizer=tokenizer)
        for r in train_records
    ]
    train_encodings = tokenizer(
        train_texts,
        padding=True,
        truncation=True,
        max_length=config.max_length,
        return_tensors="pt",
    )

    # Prepare eval data
    eval_encodings = None
    if eval_records:
        eval_texts = [
            _format_example(r["text"], r["label"], tokenizer=tokenizer)
            for r in eval_records
        ]
        eval_encodings = tokenizer(
            eval_texts,
            padding=True,
            truncation=True,
            max_length=config.max_length,
            return_tensors="pt",
        )

    # Set seed
    torch.manual_seed(config.seed)

    # Optimizer
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=config.learning_rate,
    )

    # Training loop
    dataset_size = len(train_texts)
    batch_size = min(config.batch_size, dataset_size)
    logger.info(
        "Starting causal LM training: %d samples, %d epochs, batch_size=%d",
        dataset_size,
        config.epochs,
        batch_size,
    )

    final_loss = 0.0
    for epoch in range(config.epochs):
        model.train()
        total_loss = 0.0
        num_batches = 0

        indices = torch.randperm(dataset_size)

        for start in range(0, dataset_size, batch_size):
            end = min(start + batch_size, dataset_size)
            batch_idx = indices[start:end]

            input_ids = train_encodings["input_ids"][batch_idx].to(device)
            attention_mask = train_encodings["attention_mask"][batch_idx].to(
                device
            )

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=input_ids,
            )
            loss = outputs.loss

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            total_loss += float(loss)
            num_batches += 1

        avg_loss = total_loss / max(num_batches, 1)

        # Eval loss (batched to avoid OOM on large eval sets)
        eval_msg = ""
        if eval_encodings is not None:
            model.eval()
            eval_total_loss = 0.0
            eval_n_batches = 0
            eval_size = eval_encodings["input_ids"].size(0)
            with torch.no_grad():
                for e_start in range(0, eval_size, batch_size):
                    e_end = min(e_start + batch_size, eval_size)
                    eval_ids = eval_encodings["input_ids"][e_start:e_end].to(device)
                    eval_mask = eval_encodings["attention_mask"][
                        e_start:e_end
                    ].to(device)
                    eval_out = model(
                        input_ids=eval_ids,
                        attention_mask=eval_mask,
                        labels=eval_ids,
                    )
                    eval_total_loss += float(eval_out.loss)
                    eval_n_batches += 1
            avg_eval_loss = eval_total_loss / max(eval_n_batches, 1)
            eval_msg = f", eval_loss: {avg_eval_loss:.4f}"

        logger.info(
            "Epoch %d/%d - loss: %.4f%s",
            epoch + 1,
            config.epochs,
            avg_loss,
            eval_msg,
        )
        final_loss = avg_loss

    # Merge LoRA weights and save
    logger.info("Merging LoRA weights into base model...")
    merged_model = model.merge_and_unload()
    merged_model.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))
    logger.info("Merged model saved to %s", output_path)

    return CausalTrainingResult(
        model_name=config.model_name,
        output_path=str(output_path),
        num_samples=dataset_size,
        epochs=config.epochs,
        final_loss=final_loss,
    )


def _detect_target_modules(model: Any) -> list[str]:
    """Auto-detect LoRA target modules for common architectures.

    Inspects the model's named modules to find linear projection layers
    commonly used in attention blocks.

    Args:
        model: The HuggingFace model instance.

    Returns:
        List of module name patterns to target with LoRA.
    """
    module_names = {name for name, _ in model.named_modules()}

    # Common patterns across LLM architectures
    candidates = [
        "q_proj", "v_proj", "k_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ]
    found = [c for c in candidates if any(c in name for name in module_names)]

    if found:
        return found

    # Fallback: find names of actual Linear layers in the model
    try:
        import torch.nn as nn

        linear_names = [
            name
            for name, mod in model.named_modules()
            if isinstance(mod, nn.Linear)
        ]
        if linear_names:
            logger.warning(
                "Could not detect standard attention modules. "
                "Targeting all %d Linear layers by name.",
                len(linear_names),
            )
            return linear_names
    except ImportError:
        pass

    raise ValueError(
        "Could not detect LoRA target modules. "
        "Please set lora_target_modules in your training config."
    )
