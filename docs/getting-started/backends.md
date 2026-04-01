# Backends

tobira supports multiple inference backends through the `BackendProtocol` abstraction. Choose based on your accuracy, latency, and resource requirements.

## Recommended Base Model

For new deployments, we recommend **DeBERTa-v3** over BERT. DeBERTa-v3 uses disentangled attention and an enhanced mask decoder, achieving higher classification accuracy at comparable model size.

| Model | ID | Parameters | Languages | Notes |
|-------|-----|-----------|-----------|-------|
| **mDeBERTa-v3 (recommended)** | `microsoft/mdeberta-v3-base` | 86M | Multilingual | Best for mixed-language email |
| DeBERTa-v3 Japanese | `ku-nlp/deberta-v3-base-japanese` | 86M | Japanese | Japanese-only environments |
| BERT Japanese v3 (legacy) | `tohoku-nlp/bert-base-japanese-v3` | 111M | Japanese | Current default for backward compatibility |

The BERT/ONNX backends accept any HuggingFace model name via the `model_name` configuration field. No code changes are needed to switch models — just update your `tobira.toml`.

### Migrating from BERT to DeBERTa-v3

1. Update `model_name` in your `tobira.toml`:

    ```toml
    [backend]
    type = "bert"
    model_name = "microsoft/mdeberta-v3-base"  # was: tohoku-nlp/bert-base-japanese-v3
    ```

2. If using ONNX, re-export and re-quantize:

    ```bash
    tobira train --model microsoft/mdeberta-v3-base --export-onnx
    ```

3. Run `tobira doctor` to verify the new model loads correctly.

!!! note
    Existing fine-tuned BERT models continue to work. The default `model_name` in code remains `tohoku-nlp/bert-base-japanese-v3` for backward compatibility.

## Comparison

| Backend | Model Size | Latency | Hardware | Accuracy |
|---------|-----------|---------|----------|----------|
| **FastText** | ~10 MB | ~1 ms | CPU only | Medium |
| **ONNX** | ~110 MB (quantized) | ~30 ms | CPU only | High |
| **BERT/DeBERTa** | ~340-440 MB | ~200 ms | GPU recommended | High |
| **Ollama** | 1-70 GB | ~500 ms (GPU) | GPU recommended | High |
| **Ollama + GGUF** | 0.5-4 GB | ~500 ms (GPU) | GPU recommended | High (fine-tuned) |
| **LLM API** | Remote | ~300 ms | Network | Highest |
| **Ensemble** | Varies | Varies | Varies | Highest |
| **Two-Stage** | Combined | ~1-30 ms | CPU | High |

## FastText

Lightweight n-gram model. Best for high-throughput environments where speed matters most.

```toml
[backend]
type = "fasttext"
model_path = "/var/lib/tobira/fasttext-spam.bin"
```

**When to use**: First-stage filter, resource-constrained environments, very high email volumes.

## ONNX

Quantized model running on ONNX Runtime. Best balance of accuracy and speed on CPU. Works with both BERT and DeBERTa-v3 models.

```toml
[backend]
type = "onnx"
model_path = "/var/lib/tobira/model_int8.onnx"
model_name = "microsoft/mdeberta-v3-base"  # recommended; legacy: tohoku-nlp/bert-base-japanese-v3
```

**When to use**: Production deployments on CPU-only servers, best accuracy-to-cost ratio.

## BERT / DeBERTa (PyTorch)

Full Transformer model via HuggingFace Transformers. Highest accuracy for fine-tuned models. Supports any `AutoModelForSequenceClassification`-compatible model including BERT and DeBERTa-v3.

```toml
[backend]
type = "bert"
model_name = "microsoft/mdeberta-v3-base"  # recommended; legacy: tohoku-nlp/bert-base-japanese-v3
device = "cuda"
```

**When to use**: GPU-equipped servers, when maximum fine-tuned accuracy is needed.

## Ollama

Local LLM inference via Ollama. Supports any Ollama-compatible model.

```toml
[backend]
type = "ollama"
model = "llama3"
base_url = "http://localhost:11434"
timeout = 30
```

**When to use**: When you want LLM-level understanding without external API calls.

### Ollama + Custom GGUF Model (recommended for production)

tobira can fine-tune a causal LM on your email data and export it as a GGUF model for Ollama. This gives you **LLM-level understanding with your own data** — significantly higher accuracy than generic LLMs.

```bash
# Fine-tune and export to GGUF in one command
tobira train --config config.toml --data spam.csv --output ./model \
  --model-type causal_lm

# Register with Ollama
ollama create tobira-spam -f ./model/Modelfile
```

Then use it as a backend:

```toml
[backend]
type = "ollama"
model = "tobira-spam"
base_url = "http://localhost:11434"
```

This is also a **drop-in replacement for rspamd GPT** — just change the model name in `/etc/rspamd/local.d/gpt.conf`:

```
model = "tobira-spam";
```

**When to use**: rspamd GPT + Ollama environments where you want higher accuracy from a model trained on your own data. See the [GGUF Hands-on Guide](../handson/gguf-ollama.md) for a complete walkthrough.

## LLM API

Cloud LLM via OpenAI-compatible API. Works with OpenAI, Anthropic (via proxy), and other providers.

```toml
[backend]
type = "llm_api"
model = "gpt-4o-mini"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."
timeout = 30
```

**When to use**: Highest accuracy needed, acceptable latency and cost, data privacy allows cloud processing.

## Ensemble

Combines multiple backends using weighted average or majority vote.

```toml
[backend]
type = "ensemble"
strategy = "weighted_average"
weights = [0.3, 0.7]

[[backend.backends]]
type = "fasttext"
model_path = "/var/lib/tobira/fasttext-spam.bin"

[[backend.backends]]
type = "onnx"
model_path = "/var/lib/tobira/model_int8.onnx"
```

**When to use**: Maximum accuracy through model agreement, critical environments.

## Two-Stage Filter

Routes emails through a fast first-stage model, sending only uncertain results to a precise second-stage model. Reduces load on the expensive model by 80-90%.

```toml
[backend]
type = "two_stage"

[backend.first_stage]
type = "fasttext"
model_path = "/var/lib/tobira/fasttext-spam.bin"

[backend.second_stage]
type = "onnx"
model_path = "/var/lib/tobira/model_int8.onnx"

[backend.grey_zone]
low = 0.3
high = 0.7
```

**When to use**: High-volume environments where you want both speed and accuracy.

The grey zone defines the score range where the first-stage result is uncertain:

- Score < 0.3 (low): Classified as ham by first stage, no second stage needed
- Score > 0.7 (high): Classified as spam by first stage, no second stage needed
- 0.3 <= Score <= 0.7: Grey zone, forwarded to second stage for precise classification
