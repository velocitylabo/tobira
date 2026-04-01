# GGUF エクスポート: 自社モデルを Ollama にデプロイ

tobira でファインチューニングした LLM を GGUF 形式でエクスポートし、
Ollama にデプロイするまでの完全ワークフローです。
rspamd GPT + Ollama 環境にカスタムモデルをドロップイン差し替えできます。

> **所要時間**: 約 30〜45 分
>
> **対象者**: rspamd GPT を使っているが、汎用 LLM の精度に不満がある方。
> 自社メールデータで学習した専用モデルを Ollama 経由で使いたい方。

## 目次

- [Part 1: 前提条件とインストール](#part-1-前提条件とインストール)
- [Part 2: 学習データの準備](#part-2-学習データの準備)
- [Part 3: Causal LM のファインチューニング (LoRA)](#part-3-causal-lm-のファインチューニング-lora)
- [Part 4: 量子化オプションと出力ファイル](#part-4-量子化オプションと出力ファイル)
- [Part 5: Ollama にデプロイ](#part-5-ollama-にデプロイ)
- [Part 6: rspamd GPT との統合](#part-6-rspamd-gpt-との統合)
- [Part 7: tobira バックエンドとして使う](#part-7-tobira-バックエンドとして使う)
- [トラブルシューティング](#トラブルシューティング)

---

## Part 1: 前提条件とインストール

### 必要な環境

- Python 3.9+
- GPU 推奨（CPU でも動作するが、学習に時間がかかります）
- [Ollama](https://ollama.com) がインストール済み

### インストール

```bash
pip install tobira[gguf]
```

Part 7 で tobira の API サーバーも使う場合は `serving` も追加します:

```bash
pip install tobira[gguf,serving]
```

`tobira[gguf]` により以下がインストールされます:

| パッケージ | 用途 |
|-----------|------|
| `torch` | PyTorch（モデル学習） |
| `transformers` | HuggingFace モデル読み込み |
| `peft` | LoRA アダプタ（効率的ファインチューニング） |
| `gguf` | GGUF 変換ツール |

### Ollama の確認

```bash
ollama --version
```

まだインストールしていない場合:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

---

## Part 2: 学習データの準備

学習データは CSV または JSONL 形式で、`text` と `label` カラムが必要です。

### CSV 形式

```csv
text,label
"500万円当選！今すぐ受け取り",spam
"会議の議事録を添付します",ham
"アカウントが停止されます。至急確認してください",spam
"プロジェクトの進捗報告です",ham
```

### JSONL 形式

```jsonl
{"text": "500万円当選！今すぐ受け取り", "label": "spam"}
{"text": "会議の議事録を添付します", "label": "ham"}
```

!!! tip "データ量の目安"
    - **最小**: 100 件（spam/ham 各 50 件）— PoC 用
    - **推奨**: 1,000 件以上 — 実用レベルの精度
    - **理想**: 10,000 件以上 — 本番デプロイ向け

    LoRA ファインチューニングは少量データでも効果がありますが、
    データが多いほど精度は向上します。

### 設定ファイルの作成

`train-config.toml` を作成します:

```toml
[training]
model_name = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
epochs = 3
batch_size = 4
learning_rate = 0.0002
max_length = 512
label_names = ["ham", "spam"]

# LoRA パラメータ
lora_r = 16
lora_alpha = 32
lora_dropout = 0.05
```

#### モデル選択ガイド

| モデル | パラメータ数 | VRAM | 特徴 |
|--------|------------|------|------|
| `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | 1.1B | ~3 GB | 軽量、CPU でも学習可能 |
| `microsoft/Phi-3-mini-4k-instruct` | 3.8B | ~8 GB | 高精度、GPU 推奨 |
| `google/gemma-2-2b-it` | 2B | ~5 GB | Ollama gemma2 互換 |
| `meta-llama/Llama-3.2-1B-Instruct` | 1B | ~3 GB | 最新アーキテクチャ |

!!! note "rspamd GPT との互換性"
    rspamd GPT + Ollama 環境で使う場合、元のモデルと同じアーキテクチャを
    選ぶとスムーズです。例えば `gemma2:2b` を使っている場合は
    `google/gemma-2-2b-it` をベースにします。

---

## Part 3: Causal LM のファインチューニング (LoRA)

### ワンコマンドで学習

```bash
tobira train \
  --config train-config.toml \
  --data spam_data.csv \
  --output ./my-spam-model \
  --model-type causal_lm
```

以下が自動的に実行されます:

1. **データ分割** — train/val/test に自動分割
2. **LoRA アダプタ適用** — ベースモデルの一部パラメータのみ学習（メモリ効率）
3. **ファインチューニング** — 指定エポック数の学習
4. **LoRA マージ** — アダプタをベースモデルに統合
5. **GGUF エクスポート** — Ollama 互換形式に変換
6. **Modelfile 生成** — `ollama create` 用の設定ファイル

### 学習の出力例

```
Data split: train=800, val=100, test=100
Starting causal LM fine-tuning (LoRA): TinyLlama/TinyLlama-1.1B-Chat-v1.0
  Epochs:     3
  Batch size: 4
  LoRA r:     16
LoRA: trainable=4,194,304 (0.38% of 1,100,048,384)
Epoch 1/3 - loss: 1.2345
Epoch 2/3 - loss: 0.5678
Epoch 3/3 - loss: 0.2345
Merging LoRA weights into base model...
Training complete: ./my-spam-model
Exporting to GGUF (q8_0): ./my-spam-model/model-q8_0.gguf
GGUF model saved: ./my-spam-model/model-q8_0.gguf
Ollama Modelfile saved: ./my-spam-model/Modelfile

To register with Ollama:
  ollama create tobira-spam -f ./my-spam-model/Modelfile
Then use with rspamd GPT or tobira:
  ollama run tobira-spam
```

!!! info "LoRA とは"
    LoRA（Low-Rank Adaptation）は、モデル全体ではなくアテンション層の
    低ランク行列のみを学習する手法です。全パラメータの 0.3〜1% 程度のみ
    学習するため、**メモリ使用量が大幅に削減**され、CPU でも現実的な時間で
    学習できます。

---

## Part 4: 量子化オプションと出力ファイル

Part 3 で GGUF エクスポートは自動実行済みです（デフォルト: `q8_0` 量子化）。
別の量子化タイプで再エクスポートしたい場合は `--gguf-quant-type` を指定します:

```bash
tobira train \
  --config train-config.toml \
  --data spam_data.csv \
  --output ./my-spam-model \
  --model-type causal_lm \
  --gguf-quant-type q4_0
```

学習済みモデルから GGUF のみ再生成したい場合は、Python から直接呼び出せます:

```python
from tobira.core.gguf_export import export_gguf, generate_modelfile

gguf_path = export_gguf("./my-spam-model", quant_type="q4_0")
generate_modelfile(gguf_path)
```

| 量子化 | サイズ | 精度 | 用途 |
|--------|-------|------|------|
| `f16` | 大 | 最高 | GPU 環境、精度重視 |
| `q8_0` | 中（デフォルト） | 高い | **推奨**: 精度とサイズのバランス |
| `q4_0` | 小 | 中 | メモリ制約のある環境 |

### 出力ファイル

```
my-spam-model/
  config.json           # HuggingFace モデル設定
  model.safetensors     # モデル重み
  tokenizer.json        # トークナイザ
  model-q8_0.gguf       # GGUF モデル（Ollama 用）
  Modelfile             # Ollama Modelfile
```

---

## Part 5: Ollama にデプロイ

### モデルの登録

```bash
ollama create tobira-spam -f ./my-spam-model/Modelfile
```

### 動作確認

API 経由で JSON 形式を指定して確認します:

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "tobira-spam",
  "prompt": "Classify this email:\n\n500万円当選！今すぐ受け取り",
  "format": "json",
  "stream": false
}'
```

期待されるレスポンス（`response` フィールド内）:

```json
{"label": "spam", "score": 0.97}
```

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "tobira-spam",
  "prompt": "Classify this email:\n\n会議の議事録を添付します。次回は来週火曜14:00。",
  "format": "json",
  "stream": false
}'
```

期待されるレスポンス:

```json
{"label": "ham", "score": 0.95}
```

!!! note "`ollama run` でのテスト"
    `ollama run tobira-spam "テキスト"` でもテストできますが、
    `format: json` が指定されないため、JSON 以外のテキストが返る場合があります。
    本番連携では必ず API 経由（`/api/generate` + `"format": "json"`）を使ってください。

---

## Part 6: rspamd GPT との統合

rspamd GPT モジュールが Ollama を使っている場合、モデル名を差し替えるだけで
tobira のカスタムモデルに切り替えられます。

### rspamd の設定変更

`/etc/rspamd/local.d/gpt.conf` を編集:

```
# Before (汎用 LLM)
model = "gemma2:2b";

# After (tobira でファインチューニングしたモデル)
model = "tobira-spam";
```

rspamd を再読み込み:

```bash
rspamadm configtest && systemctl reload rspamd
```

### 期待される効果

| 指標 | 汎用 LLM（変更前） | tobira モデル（変更後） |
|------|-------------------|----------------------|
| 精度 | ~85%* | **~95-97%*** |
| レイテンシ | ~500ms | ~500ms（同等） |
| API コスト | $0（ローカル） | $0（ローカル） |
| ドリフト対応 | 手動プロンプト調整 | **tobira monitor で検知 → 再学習** |

*精度は学習データの量・質・ドメインに依存します。1,000件以上のラベル付きデータで
ファインチューニングした場合の目安です。

!!! warning "重要"
    rspamd GPT のカテゴリ分類（phishing/scam/malware/marketing）は
    tobira モデルでは spam/ham の 2 値分類に変わります。
    rspamd のルールで細分類している場合は、スコア設定の調整が必要です。

---

## Part 7: tobira バックエンドとして使う

Ollama にデプロイしたカスタムモデルは、tobira 自体のバックエンドとしても使えます。

### tobira.toml の設定

```toml
[backend]
type = "ollama"
model = "tobira-spam"
base_url = "http://localhost:11434"
timeout = 30
```

### API サーバーで使用

```bash
tobira serve --config tobira.toml
```

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"text": "Win a free iPhone now!"}'
```

---

## トラブルシューティング

### `gguf` パッケージが見つからない

```
ImportError: The 'gguf' package is required for GGUF export.
```

**対処法**:

```bash
pip install tobira[gguf]
```

### GGUF 変換が失敗する

```
RuntimeError: GGUF conversion failed
```

**考えられる原因**:

1. **モデルアーキテクチャが非対応** — GGUF は LLaMA 系アーキテクチャ
   （LLaMA, Mistral, Gemma, Phi 等）をサポート。BERT 等のエンコーダモデルは
   変換できません。`--model-type causal_lm` を使ってください。

2. **変換ツールが見つからない** — tobira は `convert-hf-to-gguf` CLI を
   使いますが、PATH にない場合は `python -m gguf.convert_hf_to_gguf` に
   自動フォールバックします。両方失敗する場合は `gguf` パッケージを再インストール:
    ```bash
    pip install --force-reinstall gguf
    ```

### GPU メモリ不足

```
torch.cuda.OutOfMemoryError
```

**対処法**:

- より小さいモデルを選ぶ（TinyLlama 1.1B 推奨）
- `batch_size` を 2 または 1 に減らす
- `max_length` を 256 に減らす
- CPU で学習する（`device = "cpu"` を設定に追加）

### Ollama でモデルが応答しない

```bash
# モデルが正しく登録されたか確認
ollama list

# モデルを再作成
ollama rm tobira-spam
ollama create tobira-spam -f ./my-spam-model/Modelfile
```

---

## 次のステップ

- [tobira monitor](../cli.md#tobira-monitor) でドリフト検知を設定し、
  精度低下を自動検出
- 定期的にデータを追加して `tobira train --model-type causal_lm` で
  再学習 → `ollama create` で更新
- [Two-Stage フィルタ](../getting-started/backends.md#two-stage-filter)で
  FastText + tobira-spam の 2 段構成にする

## クリーンアップ

```bash
# Ollama モデルの削除
ollama rm tobira-spam

# 学習ファイルの削除
rm -rf ./my-spam-model
```
