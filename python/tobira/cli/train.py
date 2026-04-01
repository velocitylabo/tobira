"""tobira train - Fine-tuning pipeline (train → evaluate → export)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from tobira.errors import (
    CLI_INVALID_ARGUMENT,
    CONFIG_MISSING_SECTION,
    CONFIG_NOT_FOUND,
    DATA_EMPTY,
    DATA_INVALID_FORMAT,
    DATA_NOT_FOUND,
    format_cli_error,
)


def register(subparsers: "argparse._SubParsersAction[Any]") -> None:
    """Register the ``train`` subcommand.

    Args:
        subparsers: Subparser action from the parent parser.
    """
    parser = subparsers.add_parser(
        "train",
        help="Run fine-tuning pipeline (train → evaluate → export)",
        description="Execute the full training pipeline: data preparation, "
        "fine-tuning, evaluation, and optional ONNX/GGUF export.",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to a TOML config file. Must contain [training] section.",
    )
    parser.add_argument(
        "--data",
        required=True,
        help="Path to labelled data file (.csv or .jsonl). "
        "Required columns: text, label.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Directory to save the trained model and artifacts.",
    )
    parser.add_argument(
        "--model-type",
        choices=["classifier", "causal_lm"],
        default="classifier",
        help="Model type: 'classifier' (BERT, default) or 'causal_lm' "
        "(causal LM with LoRA for GGUF/Ollama export).",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        default=False,
        help="Skip ONNX export after training (classifier mode).",
    )
    parser.add_argument(
        "--export-gguf",
        action="store_true",
        default=False,
        help="Export model to GGUF format and generate Ollama Modelfile. "
        "Automatically enabled for causal_lm model type.",
    )
    parser.add_argument(
        "--gguf-quant-type",
        default="q8_0",
        help="GGUF quantization type (default: q8_0). "
        "Options: f32, f16, bf16, q8_0, q4_0, q4_1, q5_0, q5_1, auto.",
    )
    parser.add_argument(
        "--split-ratio",
        default="0.8,0.1,0.1",
        help="Train/val/test split ratio (default: 0.8,0.1,0.1).",
    )
    parser.set_defaults(func=_run)


def _load_labelled_data(path: Path) -> list[dict[str, str]]:
    """Load labelled data from a CSV or JSONL file.

    Args:
        path: Path to the data file.

    Returns:
        List of dicts with 'text' and 'label' keys.

    Raises:
        ValueError: If file format is unsupported or required columns missing.
    """
    suffix = path.suffix.lower()
    rows: list[dict[str, str]] = []

    if suffix == ".csv":
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "text" not in row or "label" not in row:
                    raise ValueError(
                        "CSV must contain 'text' and 'label' columns"
                    )
                rows.append(row)
    elif suffix == ".jsonl":
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    if "text" not in record or "label" not in record:
                        raise ValueError(
                            "JSONL records must contain 'text' and 'label' fields"
                        )
                    rows.append(record)
    else:
        raise ValueError(
            f"unsupported file format: {suffix!r} (expected .csv or .jsonl)"
        )

    return rows


def _parse_split_ratio(ratio_str: str) -> tuple[float, float, float]:
    """Parse a comma-separated split ratio string.

    Args:
        ratio_str: Comma-separated ratio (e.g. '0.8,0.1,0.1').

    Returns:
        Tuple of (train, val, test) ratios.

    Raises:
        ValueError: If the ratio is invalid.
    """
    parts = ratio_str.split(",")
    if len(parts) != 3:
        raise ValueError(
            f"split ratio must have 3 parts (train,val,test), got {len(parts)}"
        )
    ratios = tuple(float(p.strip()) for p in parts)
    total = sum(ratios)
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"split ratios must sum to 1.0, got {total}")
    return ratios[0], ratios[1], ratios[2]


def _split_data(
    rows: list[dict[str, str]],
    train_ratio: float,
    val_ratio: float,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Split data into train/val/test sets.

    Args:
        rows: List of data rows.
        train_ratio: Fraction for training set.
        val_ratio: Fraction for validation set.

    Returns:
        Tuple of (train, val, test) data lists.
    """
    n = len(rows)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * val_ratio)
    return rows[:train_end], rows[train_end:val_end], rows[val_end:]


def _run(args: argparse.Namespace) -> int:
    """Execute the ``train`` subcommand.

    Args:
        args: Parsed arguments from argparse.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    from tobira.config import load_toml

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(
            format_cli_error(CONFIG_NOT_FOUND, f"Config not found: {args.config}"),
            file=sys.stderr,
        )
        return 1

    try:
        config = load_toml(args.config)
    except FileNotFoundError:
        print(
            format_cli_error(CONFIG_NOT_FOUND, f"Config not found: {args.config}"),
            file=sys.stderr,
        )
        return 1

    if "training" not in config:
        print(
            format_cli_error(
                CONFIG_MISSING_SECTION,
                "Missing [training] section in config.",
                hint="Add a [training] section with model_name, epochs, etc.",
            ),
            file=sys.stderr,
        )
        return 1

    # Load data
    data_path = Path(args.data)
    if not data_path.exists():
        print(
            format_cli_error(DATA_NOT_FOUND, f"Data file not found: {args.data}"),
            file=sys.stderr,
        )
        return 1

    try:
        rows = _load_labelled_data(data_path)
    except (ValueError, Exception) as exc:
        print(
            format_cli_error(DATA_INVALID_FORMAT, f"Failed to load data: {exc}"),
            file=sys.stderr,
        )
        return 1

    if not rows:
        print(
            format_cli_error(DATA_EMPTY, "Data file is empty."),
            file=sys.stderr,
        )
        return 1

    # Parse split ratio
    try:
        train_ratio, val_ratio, _test_ratio = _parse_split_ratio(args.split_ratio)
    except ValueError as exc:
        print(
            format_cli_error(CLI_INVALID_ARGUMENT, str(exc)),
            file=sys.stderr,
        )
        return 1

    # Split data
    train_data, val_data, test_data = _split_data(rows, train_ratio, val_ratio)
    print(
        f"Data split: train={len(train_data)}, "
        f"val={len(val_data)}, test={len(test_data)}"
    )

    if not train_data:
        print(
            format_cli_error(DATA_EMPTY, "Training set is empty after split."),
            file=sys.stderr,
        )
        return 1

    # Step 1: Preprocessing (optional)
    training_config: dict[str, Any] = config["training"]
    preprocess_section = config.get("preprocessing")

    if preprocess_section:
        try:
            from tobira.preprocessing.pipeline import PreprocessingPipeline
        except ImportError:
            from tobira.errors import BACKEND_IMPORT_ERROR

            print(
                format_cli_error(
                    BACKEND_IMPORT_ERROR,
                    "preprocessing.pipeline module not available.",
                    hint="Install required dependencies: "
                    "pip install tobira[preprocessing]",
                ),
                file=sys.stderr,
            )
            return 1

        print("Running preprocessing pipeline...")
        try:
            pipeline = PreprocessingPipeline()
            for dataset in (train_data, val_data, test_data):
                for row in dataset:
                    pp_result = pipeline.run(row["text"])
                    row["text"] = pp_result.text
        except Exception as exc:
            print(
                format_cli_error(DATA_INVALID_FORMAT, f"Preprocessing failed: {exc}"),
                file=sys.stderr,
            )
            return 1
        print("Preprocessing complete.")

    output_dir = Path(args.output)

    # Dispatch based on model type
    if args.model_type == "causal_lm":
        model_name = training_config.get("model_name")
        return _run_causal_lm(args, training_config, train_data, output_dir, model_name)

    model_name = training_config.get("model_name", "bert-base-uncased")

    return _run_classifier(
        args, training_config, train_data, test_data, output_dir, model_name
    )


def _run_classifier(
    args: argparse.Namespace,
    training_config: dict[str, Any],
    train_data: list[dict[str, str]],
    test_data: list[dict[str, str]],
    output_dir: Path,
    model_name: str,
) -> int:
    """Run the BERT classifier training pipeline."""
    # Step 2: Fine-tuning
    try:
        from tobira.core.trainer import (
            TrainingConfig,
            train,
        )
    except ImportError:
        from tobira.errors import BACKEND_IMPORT_ERROR

        print(
            format_cli_error(
                BACKEND_IMPORT_ERROR,
                "core.trainer module not available.",
                hint="Install required dependencies: pip install tobira[bert]",
            ),
            file=sys.stderr,
        )
        return 1

    train_config = TrainingConfig(
        model_name=model_name,
        epochs=training_config.get("epochs", 3),
        batch_size=training_config.get("batch_size", 16),
        learning_rate=training_config.get("learning_rate", 5e-5),
        max_length=training_config.get("max_length", 512),
        device=training_config.get("device"),
        label_names=training_config.get("label_names", ["ham", "spam"]),
    )

    print(f"Starting fine-tuning: {model_name}")
    print(f"  Epochs:     {train_config.epochs}")
    print(f"  Batch size: {train_config.batch_size}")

    try:
        result = train(
            data=train_data,
            output_path=str(output_dir),
            config=train_config,
        )
    except (ImportError, RuntimeError) as exc:
        from tobira.errors import BACKEND_INFERENCE_FAILED

        print(
            format_cli_error(BACKEND_INFERENCE_FAILED, f"Training failed: {exc}"),
            file=sys.stderr,
        )
        return 1

    print(f"Training complete: {result.output_path}")

    # Step 3: Evaluation
    if test_data:
        from tobira.evaluation.metrics import compute_metrics

        test_texts = [row["text"] for row in test_data]
        test_labels = [int(row["label"]) for row in test_data]

        print("Running evaluation on test set...")
        try:
            from tobira.backends.factory import create_backend

            backend_config = {
                "type": "bert",
                "model_path": str(result.output_path),
            }
            backend = create_backend(backend_config)
            predictions = [backend.predict(t) for t in test_texts]
            y_pred = [1 if p.score >= 0.5 else 0 for p in predictions]
        except (ImportError, RuntimeError) as exc:
            print(f"Warning: could not run evaluation inference: {exc}")
            y_pred = None

        if y_pred is not None:
            metrics = compute_metrics(test_labels, y_pred)
            print()
            print("Evaluation Results:")
            print(f"  Accuracy:  {metrics.accuracy:.4f}")
            print(f"  Precision: {metrics.precision:.4f}")
            print(f"  Recall:    {metrics.recall:.4f}")
            print(f"  F1:        {metrics.f1:.4f}")
    else:
        print("No test data available, skipping evaluation.")

    # Step 4: ONNX export
    if not args.skip_export:
        from tobira.core.export import export_onnx, quantize_dynamic

        onnx_path = output_dir / "model.onnx"
        print(f"Exporting to ONNX: {onnx_path}")

        try:
            exported = export_onnx(
                model_name=str(result.output_path),
                output_path=onnx_path,
            )
            print(f"ONNX model saved: {exported}")

            quantized_path = output_dir / "model_int8.onnx"
            quantized = quantize_dynamic(exported, quantized_path)
            print(f"Quantized model saved: {quantized}")
        except (ImportError, RuntimeError) as exc:
            print(f"Warning: ONNX export failed: {exc}")
            print("Training artifacts are still available in the output directory.")
    else:
        print("ONNX export skipped (--skip-export).")

    # Optional GGUF export (for classifier models, only if explicitly requested)
    if args.export_gguf:
        _run_gguf_export(output_dir, args.gguf_quant_type, model_name)

    # Summary
    print()
    print("Training pipeline complete!")
    print(f"  Model: {model_name}")
    print(f"  Output: {output_dir}")

    return 0


def _run_causal_lm(
    args: argparse.Namespace,
    training_config: dict[str, Any],
    train_data: list[dict[str, str]],
    output_dir: Path,
    model_name: str | None,
) -> int:
    """Run the causal LM (LoRA) training pipeline with GGUF export."""
    try:
        from tobira.core.causal_trainer import (
            CausalTrainingConfig,
            train_causal,
        )
    except ImportError:
        from tobira.errors import BACKEND_IMPORT_ERROR

        print(
            format_cli_error(
                BACKEND_IMPORT_ERROR,
                "causal_trainer module not available.",
                hint="Install required dependencies: pip install tobira[gguf]",
            ),
            file=sys.stderr,
        )
        return 1

    # Default model for causal LM if not explicitly set in config
    if model_name is None:
        model_name = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"

    # Use val+test portions from --split-ratio as eval_split for causal LM
    _train_ratio, val_ratio, test_ratio = _parse_split_ratio(args.split_ratio)
    eval_split = val_ratio + test_ratio

    causal_config = CausalTrainingConfig(
        model_name=model_name,
        epochs=training_config.get("epochs", 3),
        batch_size=training_config.get("batch_size", 4),
        learning_rate=training_config.get("learning_rate", 2e-4),
        max_length=training_config.get("max_length", 512),
        device=training_config.get("device"),
        label_names=training_config.get("label_names", ["ham", "spam"]),
        lora_r=training_config.get("lora_r", 16),
        lora_alpha=training_config.get("lora_alpha", 32),
        lora_dropout=training_config.get("lora_dropout", 0.05),
        lora_target_modules=training_config.get("lora_target_modules"),
        eval_split=eval_split,
    )

    print(f"Starting causal LM fine-tuning (LoRA): {model_name}")
    print(f"  Epochs:     {causal_config.epochs}")
    print(f"  Batch size: {causal_config.batch_size}")
    print(f"  LoRA r:     {causal_config.lora_r}")

    try:
        result = train_causal(
            data=train_data,
            output_path=str(output_dir),
            config=causal_config,
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        from tobira.errors import BACKEND_INFERENCE_FAILED

        print(
            format_cli_error(BACKEND_INFERENCE_FAILED, f"Training failed: {exc}"),
            file=sys.stderr,
        )
        return 1

    print(f"Training complete: {result.output_path}")

    # GGUF export (default for causal_lm unless --skip-export)
    if not args.skip_export:
        _run_gguf_export(output_dir, args.gguf_quant_type, model_name)

    # Summary
    print()
    print("Causal LM training pipeline complete!")
    print(f"  Model: {model_name}")
    print(f"  Output: {output_dir}")

    return 0


def _run_gguf_export(
    output_dir: Path, quant_type: str, model_name: str
) -> None:
    """Run GGUF export and Modelfile generation."""
    try:
        from tobira.core.gguf_export import export_gguf, generate_modelfile
    except ImportError:
        print(
            "Warning: GGUF export not available."
            " Install with: pip install tobira[gguf]"
        )
        return

    gguf_path = output_dir / f"model-{quant_type}.gguf"
    print(f"Exporting to GGUF ({quant_type}): {gguf_path}")

    try:
        exported = export_gguf(
            model_path=output_dir,
            output_path=gguf_path,
            quant_type=quant_type,
        )
        print(f"GGUF model saved: {exported}")

        modelfile = generate_modelfile(
            gguf_path=exported,
            model_name=model_name,
        )
        print(f"Ollama Modelfile saved: {modelfile}")
        print()
        print("To register with Ollama:")
        print(f"  ollama create tobira-spam -f {modelfile}")
        print("Then use with rspamd GPT or tobira:")
        print("  ollama run tobira-spam")
    except (ImportError, RuntimeError) as exc:
        print(f"Warning: GGUF export failed: {exc}")
        print("Training artifacts are still available in the output directory.")
