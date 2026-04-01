# rspamd GPT ユーザーのための精度向上ガイド

rspamd GPT モジュール + Ollama で汎用 LLM のスパム検知をすでに運用している環境で、
tobira を使って **自社メールデータに最適化した専用モデル** に段階的にアップグレードする
完全ハンズオンです。

> **これは何？**: rspamd GPT の「汎用 LLM をそのまま使う」方式から、
> 「自社データで学習した専用モデル」に移行するための実践ガイドです。
> rspamd の設定を壊さず、段階的に精度を向上させます。

> **所要時間**: 約 60〜90 分
>
> **前提**: rspamd + GPT モジュール（`gpt.lua`）+ Ollama が稼働中

## 目次

- [全体像: 5 ステップの移行パス](#全体像-5-ステップの移行パス)
- [Part 1: 現状の精度を測定する](#part-1-現状の精度を測定する)
- [Part 2: rspamd GPT の autolearn からラベルデータを収集する](#part-2-rspamd-gpt-の-autolearn-からラベルデータを収集する)
- [Part 3: ルート A — GGUF モデルで Ollama を差し替え](#part-3-ルート-a--gguf-モデルで-ollama-を差し替え)
- [Part 4: ルート B — ONNX モデルで tobira API に切り替え](#part-4-ルート-b--onnx-モデルで-tobira-api-に切り替え)
- [Part 5: 精度モニタリングと再学習サイクル](#part-5-精度モニタリングと再学習サイクル)
- [どちらのルートを選ぶべきか](#どちらのルートを選ぶべきか)
- [トラブルシューティング](#トラブルシューティング)

---

## 全体像: 5 ステップの移行パス

```
現状                    tobira で改善
─────────────────────   ─────────────────────────────────────────

Step 1: rspamd GPT + Ollama（汎用 LLM、精度 ~85%）
           │
           ▼
Step 2: autolearn でラベルデータ蓄積（spam/ham の正解データ）
           │
           ▼
Step 3: tobira train でファインチューニング
           │
     ┌─────┴──────┐
     ▼            ▼
  ルート A      ルート B
  GGUF →        ONNX →
  Ollama        tobira API
  差し替え      に切り替え
     │            │
     ▼            ▼
Step 4: 精度 ~95-97%、rspamd はそのまま使い続ける
           │
           ▼
Step 5: tobira monitor でドリフト検知 → 再学習 → モデル更新
```

**ルート A（GGUF）**: rspamd GPT の設定を最小限の変更で済ませたい場合。
Ollama のモデル名を差し替えるだけ。

**ルート B（ONNX）**: 最高のスループットが欲しい場合。
CPU のみで 30ms/件、10 万通/日を処理可能。ただし rspamd 側に tobira プラグインの追加が必要。

---

## Part 1: 現状の精度を測定する

改善の前に、まず現状を数値で把握します。

### 1.1 テストデータの準備

rspamd のログから最近のメール判定結果を抽出し、手動でラベルを付けます。
最低 100 件（spam 50 + ham 50）あれば測定可能です。

`test_data.csv` を作成:

```csv
text,label
"500万円当選！今すぐ受け取り",spam
"会議の議事録を添付します",ham
"アカウントが停止されます。至急ログインしてください",spam
"来週の出張の件、航空券を手配しました",ham
```

!!! tip "効率的なラベリング"
    rspamd の Web UI でスパム判定ログを確認し、
    **明らかな誤判定**（FP/FN）を重点的にピックアップすると効率的です。
    完璧なデータセットより、まず測定を始めることが重要です。

### 1.2 tobira evaluate で現状精度を測定

```bash
pip install tobira[llm,evaluation]
```

rspamd GPT が使っている Ollama モデルに対して評価を実行します:

```bash
tobira evaluate \
  --data test_data.csv \
  --config current-config.toml
```

`current-config.toml` は現在の Ollama 設定を書きます:

```toml
[backend]
type = "ollama"
model = "gemma2:2b"
base_url = "http://localhost:11434"
```

### 1.3 ベースライン記録

出力例:

```
Evaluation Results:
  Accuracy:  0.8400
  Precision: 0.8200
  Recall:    0.8600
  F1:        0.8396
```

!!! info "この数値を記録しておいてください"
    ファインチューニング後に同じテストデータで再評価し、改善幅を確認します。

---

## Part 2: rspamd GPT の autolearn からラベルデータを収集する

rspamd GPT モジュールの autolearn 機能は、GPT の判定結果を Bayes フィルタに
自動フィードバックします。このデータは tobira の学習データとしても使えます。

### 2.1 rspamd の学習データをエクスポート

rspamd の Bayes トークンデータベースから直接ラベルデータを取得するのは難しいため、
**rspamd のログから判定結果を収集する**方法を使います。

```bash
# rspamd ログからスパム判定されたメールの件名を抽出
sudo journalctl -u rspamd --since "30 days ago" --no-pager | \
  grep -E "GPT_SPAM|GPT_HAM" > /tmp/rspamd_gpt_results.log
```

### 2.2 メールデータの収集

より良い学習データを作るには、実際のメール本文が必要です。
Maildir や IMAP サーバーから spam/ham フォルダのメールを取得します:

```bash
# Maildir からの収集例
mkdir -p /tmp/training_data
```

以下の Python スクリプトを `collect_emails.py` として保存し実行します:

```python
#!/usr/bin/env python3
"""Maildir から学習データを JSONL 形式で収集するスクリプト"""
import email
import json
import glob
import sys

OUTPUT = "/tmp/training_data/emails.jsonl"

# (フォルダパス, ラベル) のペアを定義
SOURCES = [
    ("/var/mail/*/cur/*", "ham"),       # 受信箱
    ("/var/mail/*/.Junk/cur/*", "spam"),  # スパムフォルダ
]

count = 0
with open(OUTPUT, "w") as out:
    for pattern, label in SOURCES:
        for path in glob.glob(pattern):
            try:
                with open(path, "rb") as fp:
                    msg = email.message_from_binary_file(fp)
                subj = str(msg.get("Subject", ""))
                body = msg.get_payload(decode=True) or b""
                text = subj + " " + body.decode("utf-8", errors="ignore")[:500]
                out.write(json.dumps({"text": text, "label": label}, ensure_ascii=False) + "\n")
                count += 1
            except Exception as e:
                print(f"SKIP {path}: {e}", file=sys.stderr)

print(f"Collected {count} emails -> {OUTPUT}")
```

```bash
python3 collect_emails.py
```

!!! warning "プライバシーに注意"
    メール本文には個人情報が含まれます。学習データはローカルに保存し、
    外部に送信しないでください。tobira の学習はすべてローカルで完結します。
    GDPR 要件がある場合は `tobira.preprocessing.anonymizer` モジュールによる PII 匿名化の利用を検討してください。

### 2.3 データの確認

```bash
# 件数確認
wc -l /tmp/training_data/emails.jsonl

# spam/ham の内訳
grep -c '"spam"' /tmp/training_data/emails.jsonl
grep -c '"ham"' /tmp/training_data/emails.jsonl
```

| データ量 | 期待精度 | 推奨 |
|---------|---------|------|
| 100 件 | ~90% | PoC には十分 |
| 500 件 | ~93% | 小規模運用向け |
| 1,000 件以上 | ~95-97% | 本番デプロイ推奨 |
| 5,000 件以上 | ~97%+ | 最高精度 |

*精度はデータの品質・ドメインにも依存します。

---

## Part 3: ルート A — GGUF モデルで Ollama を差し替え

**こちらは rspamd GPT の設定変更が最小限（モデル名の 1 行変更のみ）で済むルートです。**

### 3.1 tobira のインストール

```bash
pip install tobira[gguf]
```

### 3.2 設定ファイルの作成

`train-config.toml`:

```toml
[training]
# rspamd GPT で使っている Ollama モデルに合わせて選択
# gemma2:2b → google/gemma-2-2b-it
# llama3 → meta-llama/Llama-3.2-1B-Instruct
model_name = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
epochs = 3
batch_size = 4
learning_rate = 2e-4
max_length = 512
label_names = ["ham", "spam"]

# LoRA パラメータ（デフォルトで問題なし）
lora_r = 16
lora_alpha = 32
```

### 3.3 ファインチューニング → GGUF エクスポート

```bash
tobira train \
  --config train-config.toml \
  --data /tmp/training_data/emails.jsonl \
  --output ./rspamd-custom-model \
  --model-type causal_lm
```

完了すると以下が出力されます:

```
GGUF model saved: ./rspamd-custom-model/model-q8_0.gguf
Ollama Modelfile saved: ./rspamd-custom-model/Modelfile

To register with Ollama:
  ollama create tobira-spam -f ./rspamd-custom-model/Modelfile
```

### 3.4 Ollama にモデルを登録

```bash
ollama create tobira-spam -f ./rspamd-custom-model/Modelfile
```

API 経由で動作確認:

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "tobira-spam",
  "prompt": "Classify this email:\n\n500万円当選！今すぐ受け取り",
  "format": "json",
  "stream": false
}'
```

### 3.5 rspamd GPT のモデルを差し替え

`/etc/rspamd/local.d/gpt.conf` を編集:

```
# 変更前
# model = "gemma2:2b";

# 変更後: tobira でファインチューニングしたモデル
model = "tobira-spam";

# 他の設定はそのまま
```

!!! info "`local.d/gpt.conf` について"
    rspamd の `local.d/` ファイルは自動的に対象モジュールにスコープされるため、
    `gpt { }` ブロックで囲む必要はありません。

```bash
rspamadm configtest && sudo systemctl reload rspamd
```

!!! note "ロールバック"
    問題が起きた場合、`model = "gemma2:2b";` に戻して reload するだけで
    元の汎用 LLM に即座に戻せます。

### 3.6 改善効果を確認

Part 1 と同じテストデータで再評価:

```toml
# evaluate-config.toml
[backend]
type = "ollama"
model = "tobira-spam"
base_url = "http://localhost:11434"
```

```bash
tobira evaluate --data test_data.csv --config evaluate-config.toml
```

```
Evaluation Results:
  Accuracy:  0.9600    (was: 0.8400)
  Precision: 0.9500    (was: 0.8200)
  Recall:    0.9700    (was: 0.8600)
  F1:        0.9599    (was: 0.8396)
```

---

## Part 4: ルート B — ONNX モデルで tobira API に切り替え

**こちらは最高スループットを実現するルートです。CPU のみで 30ms/件。**

### 4.1 tobira のインストール

```bash
pip install tobira[bert,onnx,serving]
```

### 4.2 設定ファイルの作成

`train-bert-config.toml`:

```toml
[training]
model_name = "microsoft/mdeberta-v3-base"
epochs = 3
batch_size = 16
learning_rate = 5e-5
max_length = 512
label_names = ["ham", "spam"]
```

### 4.3 ファインチューニング → ONNX エクスポート

```bash
tobira train \
  --config train-bert-config.toml \
  --data /tmp/training_data/emails.jsonl \
  --output ./rspamd-onnx-model \
  --model-type classifier
```

ONNX + INT8 量子化モデルが自動生成されます:

```
Training complete: ./rspamd-onnx-model
ONNX model saved: ./rspamd-onnx-model/model.onnx
Quantized model saved: ./rspamd-onnx-model/model_int8.onnx
```

### 4.4 tobira API サーバーを起動

`tobira-api.toml`:

```toml
[backend]
type = "onnx"
model_path = "./rspamd-onnx-model/model_int8.onnx"
model_name = "microsoft/mdeberta-v3-base"
```

```bash
tobira serve --config tobira-api.toml --host 127.0.0.1 --port 8080
```

動作確認:

```bash
curl -X POST http://127.0.0.1:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"text": "500万円当選！今すぐ受け取り"}'
```

### 4.5 rspamd に tobira プラグインを追加

rspamd GPT の**代わりに**（または**並行して**）tobira Lua プラグインを使います。

tobira のソースリポジトリからプラグインファイルをコピーします:

```bash
# tobira ソースリポジトリのルートから実行
sudo cp integrations/rspamd/tobira.lua /etc/rspamd/local.d/
sudo cp integrations/rspamd/tobira.conf /etc/rspamd/local.d/
```

!!! note "pip install の場合"
    `pip install tobira` でインストールした場合は、
    [rspamd プラグイン設定](../mta/rspamd.md) からファイルをダウンロードしてください。

`/etc/rspamd/local.d/tobira.conf`:

```
tobira {
  api_url = "http://127.0.0.1:8080/predict";
  timeout = 2.0;
  fail_open = true;

  symbols {
    spam_high = "TOBIRA_SPAM_HIGH";
    spam_med = "TOBIRA_SPAM_MED";
    spam_low = "TOBIRA_SPAM_LOW";
    ham = "TOBIRA_HAM";
  }

  thresholds {
    high = 0.9;
    med = 0.7;
    low = 0.5;
    ham = 0.3;
  }

  weights {
    spam_high = 8.0;
    spam_med = 5.0;
    spam_low = 2.0;
    ham = -3.0;
  }
}
```

```bash
rspamadm configtest && sudo systemctl reload rspamd
```

### 4.6 rspamd GPT を無効化（任意）

tobira が安定動作していることを確認後、GPT モジュールを無効化できます:

```
# /etc/rspamd/local.d/gpt.conf
gpt {
  enabled = false;
}
```

!!! tip "段階的移行"
    GPT モジュールと tobira プラグインを**同時に有効**にして、
    rspamd のスコアリングで両方の結果を比較することもできます。
    tobira のスコアが安定してから GPT を無効化すると安全です。

### 4.7 改善効果を確認

```toml
# evaluate-onnx.toml
[backend]
type = "onnx"
model_path = "./rspamd-onnx-model/model_int8.onnx"
model_name = "microsoft/mdeberta-v3-base"
```

```bash
tobira evaluate --data test_data.csv --config evaluate-onnx.toml
```

---

## Part 5: 精度モニタリングと再学習サイクル

スパムの手法は常に変化します。デプロイ後の継続的なモニタリングが重要です。

### 5.1 tobira monitor の設定

`monitoring.toml` を作成:

```toml
[backend]
type = "onnx"
model_path = "./rspamd-onnx-model/model_int8.onnx"
model_name = "microsoft/mdeberta-v3-base"

[monitoring]
enabled = true
store_type = "jsonl"
log_path = "./predictions.jsonl"
```

!!! note "ルート A の場合"
    `[backend]` セクションを Ollama 設定に変更してください。

### 5.2 ドリフト検知の実行

```bash
tobira monitor --config monitoring.toml
```

出力例:

```
Drift Analysis Results:
  PSI (Population Stability Index): 0.08  [OK - < 0.1]
  KS Statistic: 0.12                      [OK - < 0.15]
  Spam ratio: 42.3%                       [Watch - was 38.1%]

  Recommendation: No retraining needed. Monitor weekly.
```

### 5.3 ウォッチモード（デーモン化）

```bash
tobira monitor --config monitoring.toml --watch --interval 3600
```

1 時間ごとにドリフトを自動チェックします。

### 5.4 再学習が必要な場合

PSI > 0.2 や KS > 0.2 が検出されたら再学習します:

```bash
# 新しいデータを追加して再学習
tobira train \
  --config train-config.toml \
  --data /tmp/training_data/emails_updated.jsonl \
  --output ./rspamd-custom-model-v2 \
  --model-type causal_lm  # ルート A の場合

# Ollama のモデルを更新（ルート A）
ollama rm tobira-spam
ollama create tobira-spam -f ./rspamd-custom-model-v2/Modelfile
```

rspamd の reload は不要です。Ollama が新しいモデルを自動的に使います。

### 5.5 再学習サイクルの目安

| 環境 | 再学習頻度 | 理由 |
|------|-----------|------|
| 一般企業 | 月 1 回 | スパム手法の変化は緩やか |
| メールプロバイダ | 週 1 回 | 大量・多様なトラフィック |
| 金融・EC | 月 2 回 | フィッシング手法の高速進化 |

---

## どちらのルートを選ぶべきか

| 観点 | ルート A（GGUF + Ollama） | ルート B（ONNX + tobira API） |
|------|--------------------------|-------------------------------|
| **rspamd 設定変更** | **1 行**（モデル名のみ） | プラグイン追加が必要 |
| **推論レイテンシ** | ~500ms（GPU 推奨） | **~30ms（CPU のみ）** |
| **スループット** | ~10 通/秒 | **~30 通/秒（CPU）** |
| **ハードウェア** | GPU 推奨 | **CPU のみで十分** |
| **rspamd GPT 機能** | autolearn 等そのまま使える | tobira 独自の機能に移行 |
| **導入の容易さ** | **非常に簡単** | やや手間がかかる |
| **精度** | 高い | 高い（同等） |

**結論:**

- **まず試したい** → ルート A（最小の変更で効果を確認）
- **大量メール処理** → ルート B（CPU 30ms、10万通/日）
- **段階的移行** → ルート A で検証 → 本番はルート B

---

## トラブルシューティング

### rspamd GPT のログが出なくなった

モデルの差し替え後、rspamd のログを確認:

```bash
sudo journalctl -u rspamd -f | grep -E "GPT|tobira"
```

GPT モジュールが Ollama に接続できていない場合:

```bash
# Ollama の状態確認
ollama list
curl http://localhost:11434/api/tags

# モデルの再登録
ollama rm tobira-spam
ollama create tobira-spam -f ./rspamd-custom-model/Modelfile
```

### rspamd GPT と tobira の判定が異なる

rspamd GPT は phishing/scam/malware/marketing のカテゴリ分類ですが、
tobira は spam/ham の 2 値分類です。rspamd のルール設定でスコアを調整してください:

```
# /etc/rspamd/local.d/groups.conf
group "tobira" {
  symbol "TOBIRA_SPAM_HIGH" {
    weight = 8.0;
    description = "tobira: high confidence spam";
  }
}
```

### 学習データが少なく精度が上がらない

- **rspamd GPT の autolearn を 1-2 ヶ月動かしてデータを蓄積**してから再挑戦
- [`tobira active-learning`](../cli.md#tobira-active-learning) で不確実なサンプルを優先的にラベリング
- 合成データの生成: `tobira` の data generation 機能を活用

### ONNX 推論のレイテンシが遅い

```bash
# モデルが INT8 量子化されているか確認
ls -la ./rspamd-onnx-model/model_int8.onnx

# CPU の AVX2 対応を確認（ONNX Runtime の高速化に必要）
lscpu | grep avx2
```

---

## 次のステップ

- [GGUF エクスポート詳細](gguf-ollama.md) — 量子化オプション、モデル選択の詳細
- [tobira CLI ワークフロー](cli.md) — init, doctor, evaluate, monitor の全体フロー
- [バックエンド比較](../getting-started/backends.md) — Two-Stage フィルタで FastText + ONNX の 2 段構成
- [rspamd プラグイン設定](../mta/rspamd.md) — ヘッダー分析、フェイルオープンの詳細設定

## クリーンアップ

```bash
# 学習データの削除
rm -rf /tmp/training_data

# モデルの削除（不要な場合）
rm -rf ./rspamd-custom-model ./rspamd-onnx-model
ollama rm tobira-spam

# rspamd を元に戻す場合
# gpt.conf: model = "gemma2:2b"; に戻す
sudo systemctl reload rspamd
```
