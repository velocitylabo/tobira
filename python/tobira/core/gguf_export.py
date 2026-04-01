"""GGUF export and Ollama Modelfile generation utilities.

Converts fine-tuned HuggingFace causal LM models to GGUF format
for deployment via Ollama, enabling drop-in replacement for
rspamd GPT + Ollama environments.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Quantization types supported by llama.cpp's convert tool.
SUPPORTED_QUANT_TYPES = frozenset(
    {"f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1", "auto"}
)

def _get_default_system_prompt() -> str:
    """Return the default system prompt from the shared prompts module."""
    from tobira.backends.prompts import SPAM_CLASSIFICATION_SYSTEM

    return SPAM_CLASSIFICATION_SYSTEM


def _find_convert_command() -> list[str]:
    """Locate the ``convert-hf-to-gguf`` CLI command.

    The command is provided by the ``gguf`` PyPI package.

    Returns:
        Command list suitable for :func:`subprocess.run`.

    Raises:
        ImportError: If the ``gguf`` package is not installed or
            the CLI command is not found on ``$PATH``.
    """
    cmd = shutil.which("convert-hf-to-gguf")
    if cmd is not None:
        return [cmd]

    # Fallback: try running as a Python module
    try:
        import gguf  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "The 'gguf' package is required for GGUF export. "
            "Install it with: pip install tobira[gguf]"
        ) from exc

    return [sys.executable, "-m", "gguf.convert_hf_to_gguf"]


def export_gguf(
    model_path: str | Path,
    output_path: str | Path | None = None,
    quant_type: str = "q8_0",
) -> Path:
    """Convert a HuggingFace causal LM to GGUF format.

    Wraps the ``convert-hf-to-gguf`` CLI tool from the ``gguf`` package
    to convert a HuggingFace-format model directory into a single
    ``.gguf`` file suitable for Ollama or llama.cpp.

    Args:
        model_path: Path to a HuggingFace model directory (must contain
            ``config.json`` and weight files).
        output_path: Path for the output ``.gguf`` file. When *None*,
            writes to ``<model_path>/model-<quant_type>.gguf``.
        quant_type: Quantization type. One of ``f32``, ``f16``, ``bf16``,
            ``q8_0``, ``q4_0``, ``q4_1``, ``q5_0``, ``q5_1``, ``auto``.
            Defaults to ``q8_0`` for a good balance of size and quality.

    Returns:
        Path to the exported GGUF file.

    Raises:
        ImportError: If the ``gguf`` package is not installed.
        FileNotFoundError: If *model_path* does not exist.
        ValueError: If *quant_type* is not supported.
        RuntimeError: If the conversion process fails.
    """
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Model directory not found: {model_path}")
    if not (model_path / "config.json").exists():
        raise FileNotFoundError(
            f"No config.json found in {model_path}. "
            "Expected a HuggingFace model directory."
        )

    if quant_type not in SUPPORTED_QUANT_TYPES:
        raise ValueError(
            f"Unsupported quant_type: {quant_type!r}. "
            f"Supported: {sorted(SUPPORTED_QUANT_TYPES)}"
        )

    if output_path is None:
        output_path = model_path / f"model-{quant_type}.gguf"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = _find_convert_command()
    cmd += [
        str(model_path),
        "--outfile",
        str(output_path),
        "--outtype",
        quant_type,
    ]

    logger.info("Running GGUF conversion: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"GGUF conversion failed (exit code {result.returncode}):\n"
            f"{result.stderr}"
        )

    if not output_path.exists():
        raise RuntimeError(
            f"GGUF conversion completed but output file not found: {output_path}"
        )

    logger.info("GGUF model exported to %s", output_path)
    return output_path


def generate_modelfile(
    gguf_path: str | Path,
    output_path: str | Path | None = None,
    system_prompt: str | None = None,
    model_name: str | None = None,
) -> Path:
    """Generate an Ollama Modelfile for a GGUF model.

    The Modelfile can be used with ``ollama create`` to register the
    fine-tuned model as a local Ollama model::

        ollama create tobira-spam -f Modelfile

    Args:
        gguf_path: Path to the ``.gguf`` model file.
        output_path: Path for the generated Modelfile. When *None*,
            writes to ``<gguf_path parent>/Modelfile``.
        system_prompt: System prompt for spam classification. Defaults
            to the standard tobira classification prompt.
        model_name: Optional model name to include as a comment.

    Returns:
        Path to the generated Modelfile.
    """
    gguf_path = Path(gguf_path)

    if output_path is None:
        output_path = gguf_path.parent / "Modelfile"
    else:
        output_path = Path(output_path)

    if system_prompt is None:
        system_prompt = _get_default_system_prompt()

    lines = []
    if model_name:
        lines.append(f"# tobira fine-tuned model: {model_name}")
    else:
        lines.append("# tobira fine-tuned spam classification model")

    lines.append(f"FROM {gguf_path.resolve()}")
    lines.append("")
    lines.append(f'SYSTEM """{system_prompt}"""')
    lines.append("")
    lines.append("PARAMETER temperature 0.1")
    lines.append("PARAMETER top_p 0.9")
    lines.append('TEMPLATE """{{ .System }}')
    lines.append("")
    lines.append("Classify this email:")
    lines.append("")
    lines.append("{{ .Prompt }}")
    lines.append('"""')
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

    logger.info("Ollama Modelfile generated at %s", output_path)
    return output_path
