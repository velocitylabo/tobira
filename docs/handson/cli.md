# tobira CLI で始めるスパム分類ワークフロー

tobira の CLI コマンドを使って、モデル準備から API サーバー起動、
評価、モニタリングまで一通りのワークフローを体験するハンズオンです。
Docker は不要で、Python 環境のみで完結します。

> **所要時間**: 約 40〜60 分

## 目次

- [Part 1: 前提条件とインストール](#part-1-前提条件とインストール)
- [Part 2: FastText モデルの準備](#part-2-fasttext-モデルの準備)
- [Part 3: tobira init — MTA 自動検出と設定生成](#part-3-tobira-init--mta-自動検出と設定生成)
- [Part 4: 設定ファイルの作成](#part-4-設定ファイルの作成)
- [Part 5: tobira doctor — 設定診断](#part-5-tobira-doctor--設定診断)
- [Part 6: tobira serve + API テスト](#part-6-tobira-serve--api-テスト)
- [Part 7: tobira evaluate — モデル評価](#part-7-tobira-evaluate--モデル評価)
- [Part 8: tobira monitor — ドリフト検出](#part-8-tobira-monitor--ドリフト検出)
- [次のステップ](#次のステップ)
- [クリーンアップ](#クリーンアップ)

---

## Part 1: 前提条件とインストール

### 必要な環境

- Python 3.9+

### インストール

```bash
pip install tobira[serving,fasttext]
```

### CLI コマンドの確認

```bash
tobira --help
```

主要なサブコマンド:

| コマンド | 説明 |
|---|---|
| `tobira init` | MTA 自動検出 + 設定ファイル生成 |
| `tobira serve` | API サーバー起動 |
| `tobira doctor` | 設定の診断チェック |
| `tobira evaluate` | モデル評価（精度、F1 等） |
| `tobira monitor` | 予測ログのドリフト検出 |
| `tobira active-learning` | Active Learning キュー管理 |
| `tobira ab-test` | A/B テスト結果の確認 |

---

## Part 2: FastText モデルの準備

API サーバーを動かすにはバックエンドモデルが必要です。
ここでは FastText モデルを学習します。

> 詳細な説明は [FastText ハンズオン](fasttext.md) Part 2〜3 を参照してください。

```bash
# 作業ディレクトリに移動（サンプルデータがある場所）
cd docs/handson

# CSV → FastText 形式に変換
python3 -c "
import csv
with open('sample_train.csv') as f, open('train.txt', 'w') as out:
    for row in csv.DictReader(f):
        out.write(f'__label__{row[\"label\"]} {row[\"text\"]}\n')
print('train.txt を作成しました')
"

# モデルを学習
python3 -c "
import fasttext
model = fasttext.train_supervised('train.txt', epoch=25, lr=1.0, wordNgrams=2)
model.save_model('fasttext-spam.bin')
print('fasttext-spam.bin を作成しました')
"
```

---

## Part 3: tobira init — MTA 自動検出と設定生成

`tobira init` はインストール済みの MTA（rspamd、SpamAssassin、Haraka、Postfix）を
自動検出し、対応する設定ファイルを生成するウィザードです。

```bash
tobira init
```

### MTA が検出された場合

```
Detecting MTA services...
  Found: rspamd (via systemctl)

Using detected MTA: rspamd
...
```

対応する設定ファイル（`tobira.conf`、`tobira.lua` 等）が生成されます。

### MTA が検出されない場合

```
Detecting MTA services...
No MTA services detected.

Select MTA to configure:
  1. rspamd
  2. spamassassin
  3. haraka
  4. postfix
>
```

手動で MTA を選択できます。

> **Note**: このハンズオンでは MTA 連携は行いません。
> `tobira init` の動作を確認するだけで OK です。
> MTA 連携テストは [Docker ハンズオン](../../docker/HANDS_ON.md) Part 3 を参照してください。

### オプション

```bash
# API URL を指定して生成
tobira init --api-url http://mail.example.com:8000

# 出力先ディレクトリを指定
tobira init --output-dir /tmp/tobira-config
```

---

## Part 4: 設定ファイルの作成

tobira の全機能を制御する TOML 設定ファイルを手動で作成します。

```bash
cat > tobira.toml << 'EOF'
# === バックエンド ===
[backend]
type = "fasttext"
model_path = "./fasttext-spam.bin"

# === 予測ログ（モニタリング用） ===
[monitoring]
enabled = true
store_type = "jsonl"
log_path = "./predictions.jsonl"

# === ユーザーフィードバック ===
[feedback]
enabled = true
store_path = "./feedback.jsonl"

# === メールヘッダー分析 ===
[header_analysis]
enabled = true
weight = 0.3

# === Active Learning ===
[active_learning]
enabled = true
strategy = "entropy"
uncertainty_threshold = 0.3
max_queue_size = 100
queue_path = "./al_queue.jsonl"
EOF
```

### 設定セクションの解説

| セクション | 役割 |
|---|---|
| `[backend]` | 分類バックエンドの種類とモデルパス |
| `[monitoring]` | 予測結果の JSONL ログ出力（ドリフト検出に使用） |
| `[feedback]` | ユーザーからの誤分類報告を記録 |
| `[header_analysis]` | SPF/DKIM/DMARC ヘッダーのリスク分析 |
| `[active_learning]` | 不確実なサンプルのラベリングキュー |

> 全設定オプションの詳細は [Configuration ガイド](../getting-started/configuration.md) を参照してください。

---

## Part 5: tobira doctor — 設定診断

`tobira doctor` は設定ファイルの整合性をチェックする診断ツールです。

```bash
tobira doctor --config tobira.toml
```

### 期待される出力

```
  ✅  Config file is valid TOML
  ✅  Backend model file exists: ./fasttext-spam.bin
  ✅  Backend initialized successfully (fasttext)
  ✅  API key: not configured (optional)
  ✅  Serving dependencies available (fastapi, uvicorn)
  ✅  Monitoring log_path is writable: ./predictions.jsonl
  ✅  Feedback store_path is writable: ./feedback.jsonl
  ✅  Active Learning queue_path is writable: ./al_queue.jsonl

All checks passed.
```

### エラーが出た場合

```
  ❌  Backend model file not found: ./fasttext-spam.bin
```

→ Part 2 のモデル学習を再実行してください。

### API サーバーとの接続チェック

サーバー起動後に `--api-url` オプションで接続確認もできます:

```bash
tobira doctor --config tobira.toml --api-url http://127.0.0.1:8000
```

---

## Part 6: tobira serve + API テスト

### サーバーの起動

```bash
tobira serve --config tobira.toml
```

```
INFO:     Started server process
INFO:     Uvicorn running on http://127.0.0.1:8000
```

別のターミナルを開いて、以下のテストを実行します。

### ヘルスチェック

```bash
# 基本ヘルスチェック
curl -s http://127.0.0.1:8000/v1/health | python3 -m json.tool

# Kubernetes 用
curl -s http://127.0.0.1:8000/v1/health/ready | python3 -m json.tool
curl -s http://127.0.0.1:8000/v1/health/live | python3 -m json.tool
```

### ham メールの分類

```bash
curl -s -X POST http://127.0.0.1:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hi Bob, can we meet at 3pm tomorrow to discuss the project?"}' \
  | python3 -m json.tool
```

### spam メールの分類

```bash
curl -s -X POST http://127.0.0.1:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "Congratulations! You won a free iPhone! Click here to claim now!"}' \
  | python3 -m json.tool
```

### ヘッダー分析付き予測

SPF/DKIM/DMARC の認証結果を含めて分類できます:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Your account needs verification. Click the link below.",
    "headers": {
      "spf": "fail",
      "dkim": "fail",
      "dmarc": "fail"
    }
  }' | python3 -m json.tool
```

`header_score` フィールドにヘッダーリスクスコアが含まれます。

### フィードバックの送信

誤分類を報告する API です:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/feedback \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Please review the Q3 budget report attached.",
    "label": "ham",
    "source": "user"
  }' | python3 -m json.tool
```

```json
{
    "status": "accepted",
    "id": "fb-..."
}
```

### 予測ログの確認

`[monitoring]` を有効にしたので、予測結果が JSONL ファイルに記録されています:

```bash
cat predictions.jsonl | python3 -m json.tool --no-ensure-ascii | head -20
```

### 複数の予測を実行（Part 8 の準備）

ドリフト検出に十分なデータを蓄積するため、複数の予測を実行します:

```bash
# ham メール群
for text in \
  "The sprint retrospective is at 4pm today." \
  "Please review the updated architecture diagram." \
  "Weekly status report: all milestones on track." \
  "The CI pipeline needs a fix for the flaky test." \
  "Agenda for tomorrow: budget review, hiring update." \
  "The staging environment has been updated." \
  "Could you review PR #42 when you get a chance?" \
  "The database migration completed successfully."; do
  curl -s -X POST http://127.0.0.1:8000/v1/predict \
    -H 'Content-Type: application/json' \
    -d "{\"text\": \"$text\"}" > /dev/null
done

# spam メール群
for text in \
  "WINNER! Claim your prize now! Act immediately!" \
  "Get cheap medications online! No prescription!" \
  "Your bank account is locked. Click to unlock!" \
  "Make money fast! Guaranteed returns! Zero risk!" \
  "Free trial! Enter credit card to continue!" \
  "Urgent wire transfer needed! Send bank details!" \
  "Lose 20 pounds in 7 days! Buy now!" \
  "Casino bonus: Get free chips! Play and win!"; do
  curl -s -X POST http://127.0.0.1:8000/v1/predict \
    -H 'Content-Type: application/json' \
    -d "{\"text\": \"$text\"}" > /dev/null
done

echo "予測ログに $(wc -l < predictions.jsonl) 件記録されました"
```

---

## Part 7: tobira evaluate — モデル評価

### テストデータの形式

`sample_test.csv` を使用します（20 件: ham 10 件 + spam 10 件）。

```bash
head -5 sample_test.csv
```

```
text,label
"The sprint retrospective is at 4pm today in room 301.",0
"Please review the updated architecture diagram before EOD.",0
...
```

> **重要**: `tobira evaluate` はラベルを整数（`0` = ham、`1` = spam）で期待します。
> FastText の学習データ（`spam`/`ham` 文字列）とは形式が異なるので注意してください。

### 評価の実行

```bash
tobira evaluate sample_test.csv --config tobira.toml
```

期待される出力:

```
Accuracy:  0.85
Precision: 0.90
Recall:    0.80
F1:        0.85
```

> スコアは学習データの量・質に依存します。50 件のサンプルデータでは
> 本番品質には達しませんが、ワークフローの確認には十分です。

### 最適閾値の探索

```bash
tobira evaluate sample_test.csv --config tobira.toml --tune-threshold
```

F1 スコアが最大になる閾値を自動で探索します。

---

## Part 8: tobira monitor — ドリフト検出

Part 6 で蓄積した予測ログを分析し、スコア分布の偏りやドリフトを検出します。

```bash
tobira monitor predictions.jsonl
```

### 出力の読み方

| 指標 | 説明 |
|---|---|
| PSI (Population Stability Index) | スコア分布の安定性。> 0.2 で要注意 |
| KS statistic | 分布の統計的差異 |
| FP/FN rate | 偽陽性・偽陰性の割合（フィードバックデータがある場合） |
| Threshold suggestion | F1 最適化に基づく閾値の提案 |

### JSON 出力

```bash
tobira monitor predictions.jsonl --format json | python3 -m json.tool
```

マシンリーダブルな形式で出力されます。CI/CD パイプラインや自動化に便利です。

### ウォッチモード（本番用）

```bash
# 5 分ごとに自動分析（Ctrl+C で停止）
tobira monitor predictions.jsonl --watch --interval 300
```

---

## 次のステップ

このハンズオンで体験した CLI ワークフローの先には、さらに以下の機能があります:

### MTA 連携テスト

Docker 環境で Haraka、rspamd、SpamAssassin との連携をテスト:

→ [Docker ハンズオン](../../docker/HANDS_ON.md) Part 3

### BERT/DeBERTa モデルの学習

より高精度なモデルを学習:

```bash
tobira train --config train.toml --data labeled_emails.csv --output ./bert_model
```

### Knowledge Distillation

大きなモデルを小さなモデルに蒸留:

```bash
tobira distill --config distill.toml --data emails.csv --output ./student_model
```

### モデルの共有

HuggingFace Hub にモデルを公開:

```bash
tobira hub-push ./bert_model --repo-id your-org/tobira-spam-model
tobira hub-pull your-org/tobira-spam-model --local-dir ./downloaded_model
```

---

## クリーンアップ

```bash
rm -f train.txt fasttext-spam.bin tobira.toml
rm -f predictions.jsonl feedback.jsonl al_queue.jsonl
```
