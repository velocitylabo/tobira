# CLI Reference

The `tobira` command provides subcommands for server management, diagnostics, evaluation, and monitoring.

## Installation

```bash
pip install tobira[serving]
```

## Getting Started

### `tobira init`

Auto-detect your MTA and generate integration configuration files.

```bash
tobira init [--mta MTA] [--output-dir DIR]
```

The setup wizard:

1. Detects running MTAs (rspamd, SpamAssassin, Haraka, Postfix)
2. Generates MTA-specific plugin configuration
3. Provides step-by-step installation instructions

### `tobira serve`

Start the FastAPI API server.

```bash
tobira serve [--config CONFIG] [--host HOST] [--port PORT] [--backend BACKEND]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--config` | — | Path to TOML configuration file |
| `--host` | `127.0.0.1` | Server bind address |
| `--port` | `8000` | Server bind port |
| `--backend` | — | Backend type (overrides config) |
| `--model-path` | — | Model file path (overrides config) |

### `tobira doctor`

Run diagnostic checks on your tobira installation.

```bash
tobira doctor [--config CONFIG]
```

Checks performed:

- Configuration file validity
- Backend model loading
- API server connectivity
- MTA plugin activation status

### `tobira demo`

Launch a full demonstration environment using Docker Compose.

```bash
tobira demo [--backend BACKEND]
```

Starts the API server, MTA plugins, and monitoring stack for interactive evaluation. Useful for trying tobira without configuring your production MTA.

## Training & Evaluation

### `tobira train`

Fine-tune a model on labeled email data. Supports two model types:

- **classifier** (default): BERT/DeBERTa encoder model → ONNX export
- **causal_lm**: Causal LM with LoRA → GGUF export for Ollama

#### Classifier mode (default)

```bash
tobira train --config CONFIG --data DATA --output OUTPUT
```

#### Causal LM mode (for GGUF/Ollama)

```bash
tobira train --config CONFIG --data DATA --output OUTPUT \
  --model-type causal_lm
```

This runs: LoRA fine-tuning → weight merging → GGUF export → Ollama Modelfile generation.

| Option | Default | Description |
|--------|---------|-------------|
| `--config` | — | Configuration file path (must contain `[training]` section) |
| `--data` | — | Labeled data file (CSV or JSONL with `text`, `label` columns) |
| `--output` | — | Output directory for trained model |
| `--model-type` | `classifier` | `classifier` (BERT) or `causal_lm` (LoRA → GGUF) |
| `--skip-export` | `false` | Skip ONNX export (classifier) or GGUF export (causal_lm) |
| `--export-gguf` | `false` | Export to GGUF format (also works in classifier mode) |
| `--gguf-quant-type` | `q8_0` | GGUF quantization: `f32`, `f16`, `bf16`, `q8_0`, `q4_0`, `q4_1`, `q5_0`, `q5_1`, `auto` |
| `--split-ratio` | `0.8,0.1,0.1` | Train/val/test split ratio |

#### Training config (`[training]` section in TOML)

**Common options:**

| Key | Default | Description |
|-----|---------|-------------|
| `model_name` | `bert-base-uncased` / `TinyLlama/...` | HuggingFace model name |
| `epochs` | `3` | Number of training epochs |
| `batch_size` | `16` (classifier) / `4` (causal_lm) | Training batch size |
| `learning_rate` | `5e-5` (classifier) / `2e-4` (causal_lm) | Peak learning rate |
| `max_length` | `512` | Maximum token sequence length |
| `device` | auto | `cpu` or `cuda` |
| `label_names` | `["ham", "spam"]` | Classification label names |

**Causal LM (LoRA) options:**

| Key | Default | Description |
|-----|---------|-------------|
| `lora_r` | `16` | LoRA rank |
| `lora_alpha` | `32` | LoRA scaling factor |
| `lora_dropout` | `0.05` | LoRA dropout probability |
| `lora_target_modules` | auto-detect | Modules to apply LoRA to |

See the [GGUF Hands-on Guide](handson/gguf-ollama.md) for a complete walkthrough.

### `tobira evaluate`

Evaluate a backend against labeled test data.

```bash
tobira evaluate --data DATA [--backend BACKEND] [--config CONFIG]
```

| Option | Description |
|--------|-------------|
| `--data` | Path to labeled data file (JSONL) |
| `--backend` | Backend type to evaluate |
| `--config` | Configuration file path |

Outputs: accuracy, precision, recall, F1 score, confusion matrix, and PR curve.

### `tobira monitor`

Analyze prediction metrics and suggest improvements.

```bash
tobira monitor [--config CONFIG] [--watch] [--interval SECONDS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--config` | — | Configuration file path |
| `--watch` | — | Enable daemon mode (continuous monitoring) |
| `--interval` | `3600` | Check interval in seconds (daemon mode) |

Analysis includes:

- Score distribution shift detection (PSI / KS test)
- FP/FN rate trends
- Threshold tuning suggestions
- Backend upgrade recommendations

## Advanced

### `tobira distill`

Run knowledge distillation from a teacher model to a student model.

```bash
tobira distill --teacher TEACHER --student STUDENT --data DATA
```

| Option | Description |
|--------|-------------|
| `--teacher` | Teacher model path or name |
| `--student` | Student model path or name |
| `--data` | Training data path |

### `tobira ab-test`

Run A/B testing between model variants in production.

```bash
tobira ab-test --config CONFIG
```

Supports random and hash-based traffic splitting with variant analytics.

### `tobira active-learning`

Manage the active learning queue for uncertainty-based sample selection.

```bash
tobira active-learning --config CONFIG [--strategy STRATEGY]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--config` | — | Configuration file path |
| `--strategy` | `entropy` | Sampling strategy (`entropy`, `bald`, `margin`) |

### `tobira hub-push` / `tobira hub-pull`

Manage models on HuggingFace Hub.

```bash
# Push a model to HuggingFace Hub
tobira hub-push --model-path MODEL --repo REPO

# Pull a model from HuggingFace Hub
tobira hub-pull --repo REPO --output-dir DIR
```

### `tobira milter`

Start the Postfix milter daemon.

```bash
tobira milter --config CONFIG
```

See [Postfix milter integration](mta/postfix-milter.md) for configuration details.
