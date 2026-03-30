# tobira Docker ハンズオン — 全機能ガイド

tobira の全機能を Docker 環境で体験するガイドです。
基本的な spam 判定から、ヘッダー分析、AI 生成テキスト検出、
Active Learning、A/B テスト、HA 構成まで一通り試せます。

> **所要時間**: mock モード全体で約 30 分、real モード追加で +15 分

## 目次

- [前提条件](#前提条件)
- [2 つのモード](#2-つのモード)
- [アーキテクチャ](#アーキテクチャ)
- [Part 1: 起動と基本テスト](#part-1-起動と基本テスト)
- [Part 2: API 全機能テスト](#part-2-api-全機能テスト)
- [Part 3: MTA 連携テスト](#part-3-mta-連携テスト)
- [Part 4: Active Learning](#part-4-active-learning)
- [Part 5: A/B テスト](#part-5-ab-テスト)
- [Part 6: ダッシュボード](#part-6-ダッシュボード)
- [Part 7: HA 構成（高可用性）](#part-7-ha-構成高可用性)
- [Part 8: 設定ファイルリファレンス](#part-8-設定ファイルリファレンス)
- [Part 9: CLI コマンド概要](#part-9-cli-コマンド概要)
- [Part 10: 本番ロールアウト戦略](#part-10-本番ロールアウト戦略)
- [クリーンアップ](#クリーンアップ)
- [トラブルシューティング](#トラブルシューティング)

---

## 前提条件

- Docker Engine 20.10+
- Docker Compose v2+

```bash
docker --version
docker compose version
```

---

## 2 つのモード

| モード | API サーバー | ML モデル | 起動時間 | 用途 |
|---|---|---|---|---|
| **mock** (デフォルト) | ルールベース分類器 | 不要 | 数秒 | 全機能の動作確認・CI |
| **real** | 本物の tobira + Ollama | gemma2:2b (~2GB) | 初回数分 | ML推論の体験・本番相当テスト |

---

## アーキテクチャ

### mock モード

```
┌──────────┐  SMTP   ┌──────────┐  HTTP POST   ┌─────────────┐
│  あなた   │───────→│  Haraka   │────────────→│  tobira-api │
└──────────┘ :2525   └──────────┘ /v1/predict  │  (mock)     │
                                                │  :8000      │
┌──────────┐  HTTP   ┌──────────┐  HTTP POST   │  キーワード  │
│  あなた   │───────→│  rspamd  │────────────→│  マッチで    │
└──────────┘ :11333  └──────────┘ /v1/predict  │  分類       │
                                                │             │
┌──────────┐  spamc  ┌──────────────┐ HTTP POST│             │
│  あなた   │───────→│ SpamAssassin │─────────→│             │
└──────────┘ :783    └──────────────┘/v1/predict└─────────────┘
```

### real モード

```
┌──────────┐  SMTP   ┌──────────┐              ┌─────────────┐     ┌──────────┐
│  あなた   │───────→│  Haraka   │─────────────│  tobira-api │────→│  Ollama  │
└──────────┘ :2525   └──────────┘  /v1/predict │  (real)     │     │  :11434  │
                                                │  :8000      │     │ gemma2:2b│
┌──────────┐  HTTP   ┌──────────┐              │             │     └──────────┘
│  あなた   │───────→│  rspamd  │─────────────│  ML推論で   │
└──────────┘ :11333  └──────────┘  /v1/predict │  分類       │
                                                │             │
┌──────────┐  spamc  ┌──────────────┐          │             │
│  あなた   │───────→│ SpamAssassin │──────────│             │
└──────────┘ :783    └──────────────┘/v1/predict└─────────────┘
```

---

## Part 1: 起動と基本テスト

### Step 1-1: mock モードで起動（推奨：まずこちらから）

```bash
cd docker
docker compose up --build -d
```

### Step 1-2: real モードで起動（ML モデルを使う場合）

```bash
cd docker
docker compose -f docker-compose.real.yml up --build -d
```

> **初回のみ**: Ollama の gemma2:2b モデル (~2GB) のダウンロードに数分かかります。

起動状態を確認:

```bash
docker compose ps
# real モードの場合: docker compose -f docker-compose.real.yml ps
```

すべてのサービスが `running` (tobira-api は `healthy`) になっていれば OK です。

> **Note**: 以降のステップでは mock モードの `docker compose` コマンドで記載しています。
> real モードの場合は `-f docker-compose.real.yml` を追加してください。

### Step 1-3: ヘルスチェック（3 種類）

```bash
# 基本ヘルスチェック
curl -s http://localhost:8000/v1/health | python3 -m json.tool
```

```json
{ "status": "ok" }
```

```bash
# Kubernetes readiness probe — トラフィック受付可否
curl -s http://localhost:8000/v1/health/ready | python3 -m json.tool
```

```json
{ "ready": true, "reason": null }
```

```bash
# Kubernetes liveness probe — プロセス生存確認
curl -s http://localhost:8000/v1/health/live | python3 -m json.tool
```

```json
{ "alive": true }
```

> **ポイント**: `/health/ready` と `/health/live` は Kubernetes の
> readinessProbe / livenessProbe として利用できます。

### Step 1-4: 基本的な ham / spam 判定

```bash
# ham（正常メール）
curl -s -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hi, can we schedule our weekly meeting for Thursday?"}' \
  | python3 -m json.tool
```

```json
{
    "label": "ham",
    "score": 0.91,
    "labels": { "spam": 0.09, "ham": 0.91 },
    "language": "en",
    "ai_generated": { "is_ai_generated": false, "confidence": 0.0 },
    "model_version": "mock-1.0"
}
```

```bash
# spam
curl -s -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "Buy now! Free offer! Click here for your lottery winner prize!"}' \
  | python3 -m json.tool
```

```json
{
    "label": "spam",
    "score": 0.95,
    "labels": { "spam": 0.95, "ham": 0.05 },
    "language": "en",
    "ai_generated": { "is_ai_generated": false, "confidence": 0.0 },
    "model_version": "mock-1.0"
}
```

> **mock モード**: キーワードが 3 個以上→score=0.95、2 個→0.80、1 個→0.60
>
> **real モード**: LLM がメール文面の意味を理解して分類。キーワードがなくても詐欺的な文面なら spam 判定。

---

## Part 2: API 全機能テスト

### Step 2-1: ヘッダー分析

メールヘッダー（SPF / DKIM / DMARC 等）の認証結果を送信すると、
ヘッダーベースのリスクスコアも返されます。

```bash
# SPF=fail, DKIM=fail → ヘッダーリスク高
curl -s -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Please review the attached invoice.",
    "headers": {
      "spf": "fail",
      "dkim": "fail",
      "dmarc": "fail",
      "from_addr": "ceo@company.com",
      "reply_to": "attacker@evil.com"
    }
  }' | python3 -m json.tool
```

```json
{
    "label": "ham",
    "score": 0.88,
    "labels": { "spam": 0.12, "ham": 0.88 },
    "header_score": 0.6,
    "language": "en",
    "ai_generated": { "is_ai_generated": false, "confidence": 0.0 },
    "model_version": "mock-1.0"
}
```

> **ポイント**: `header_score` が 0.6 — SPF fail (+0.15), DKIM fail (+0.15),
> DMARC fail (+0.20), From≠Reply-To (+0.10) の合計。
> テキスト判定は ham でもヘッダーリスクが高く、総合判断に利用できます。

```bash
# SPF=pass, DKIM=pass → ヘッダーリスク低
curl -s -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Please review the attached invoice.",
    "headers": {
      "spf": "pass",
      "dkim": "pass",
      "dmarc": "pass",
      "from_addr": "alice@company.com",
      "reply_to": "alice@company.com"
    }
  }' | python3 -m json.tool
```

`header_score` が 0.0 になることを確認してください。

### Step 2-2: 判定理由の取得（explain）

`"explain": true` を指定すると、判定に寄与したトークンの attribution が返されます。

```bash
curl -s -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Buy now! Free offer! Click here!",
    "explain": true
  }' | python3 -m json.tool
```

```json
{
    "label": "spam",
    "score": 0.95,
    "labels": { "spam": 0.95, "ham": 0.05 },
    "language": "en",
    "explanations": [
        { "token": "buy now", "attribution": 0.15, "type": "keyword_match" },
        { "token": "free offer", "attribution": 0.15, "type": "keyword_match" },
        { "token": "click here", "attribution": 0.15, "type": "keyword_match" }
    ],
    "model_version": "mock-1.0"
}
```

```bash
# ヘッダーと explain を組み合わせる
curl -s -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Buy now! Free offer! Click here!",
    "headers": { "spf": "fail", "dkim": "fail" },
    "explain": true
  }' | python3 -m json.tool
```

`explanations` にヘッダーリスクの attribution も追加されます。

### Step 2-3: 言語指定

```bash
# 日本語メールの判定
curl -s -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "お世話になっております。来週の会議について確認させてください。",
    "language": "ja"
  }' | python3 -m json.tool
```

`"language": "ja"` が返されます。language を省略した場合、
日本語文字が含まれていれば自動で `ja` と検出されます。

### Step 2-4: AI 生成テキスト検出

AI が生成した文面（フィッシング等で利用される）を検出します。

```bash
# AI 生成パターンを含むテキスト
curl -s -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "As an AI, I would like to delve into a comprehensive overview of this topic. It is important to note that we must facilitate better communication."
  }' | python3 -m json.tool
```

```json
{
    "label": "ham",
    "ai_generated": {
        "is_ai_generated": true,
        "confidence": 0.9
    }
}
```

> **ポイント**: `ai_generated.is_ai_generated` が `true` の場合、
> AI で生成された文面の可能性があります。confidence が高いほど確信度が高い。

```bash
# 人間が書いた普通のメール
curl -s -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hey, are you free for lunch tomorrow? I was thinking of trying that new ramen place."}' \
  | python3 -m json.tool
```

`ai_generated.is_ai_generated` が `false`、confidence が 0.0 になります。

### Step 2-5: フィードバック送信

誤分類を報告するフィードバック API です。

```bash
# 「このメールは本当は spam だった」とフィードバック
curl -s -X POST http://localhost:8000/v1/feedback \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Exclusive deal just for you, act now before it expires!",
    "label": "spam",
    "source": "user-report"
  }' | python3 -m json.tool
```

```json
{
    "status": "accepted",
    "id": "fb-a1b2c3d4"
}
```

> **ポイント**: フィードバックデータは再学習やモデル評価に利用されます。
> `source` でフィードバック元を区別できます（user-report, admin, automated 等）。

---

## Part 3: MTA 連携テスト

### Step 3-1: Haraka（SMTP）経由

Haraka は SMTP サーバーとして動作し、`data_post` フックで tobira API を呼び出します。

```bash
# ham メールを送信
python3 -c "
import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg['From'] = 'alice@example.com'
msg['To'] = 'bob@example.com'
msg['Subject'] = 'Meeting tomorrow'
msg.set_content('Hi Bob, can we meet at 3pm tomorrow to discuss the project?')

try:
    with smtplib.SMTP('localhost', 2525, timeout=10) as s:
        s.send_message(msg)
    print('Result: accepted')
except smtplib.SMTPDataError as e:
    print(f'Result: rejected by tobira - {e}')
"
```

期待される出力: `Result: accepted`（ham なのでそのまま受け入れ）

```bash
# spam メールを送信
python3 -c "
import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg['From'] = 'spammer@example.com'
msg['To'] = 'victim@example.com'
msg['Subject'] = 'You are a winner!'
msg.set_content('Buy now! Free offer! Click here for your lottery winner prize! Act now!')

try:
    with smtplib.SMTP('localhost', 2525, timeout=10) as s:
        s.send_message(msg)
    print('Result: accepted (spam was not blocked)')
except smtplib.SMTPDataError as e:
    print(f'Result: REJECTED by tobira plugin! - {e}')
"
```

期待される出力: `Result: REJECTED by tobira plugin! - ...`（spam として拒否）

```bash
# Haraka ログを確認
docker compose logs haraka --tail 20
```

#### Haraka 設定リファレンス（本番用）

| 設定項目 | デフォルト | 説明 |
|---|---|---|
| `url` | `http://127.0.0.1:8000` | tobira API のアドレス |
| `timeout` | `5000` | タイムアウト (ms) |
| `threshold` | `0.5` | spam 判定の閾値 |
| `reject_spam` | `true` | 閾値超過時に reject するか |
| `send_headers` | `false` | SPF/DKIM/DMARC ヘッダーを送信するか |

### Step 3-2: rspamd 経由

rspamd は HTTP API (`/checkv2`) でメールをスキャンし、
tobira プラグインが `TOBIRA_*` シンボルを挿入します。

```bash
# ham メールをスキャン
curl -s -X POST http://localhost:11333/checkv2 --data-binary \
'From: alice@example.com
To: bob@example.com
Subject: Normal email
Content-Type: text/plain; charset=utf-8

Hi, this is a perfectly normal business email about our quarterly review.' \
  | python3 -m json.tool
```

レスポンスの `symbols` セクションに `TOBIRA_HAM` が含まれていれば成功です。

```bash
# spam メールをスキャン
curl -s -X POST http://localhost:11333/checkv2 --data-binary \
'From: spammer@example.com
To: victim@example.com
Subject: Winner!
Content-Type: text/plain; charset=utf-8

Buy now! Free offer! Click here for your lottery winner prize! Act now! Urgent discount casino!' \
  | python3 -m json.tool
```

`TOBIRA_SPAM_HIGH` が含まれていれば成功です。

```bash
# rspamd ログを確認
docker compose logs rspamd | grep tobira
```

#### rspamd シンボルとスコアの対応

| シンボル | weight | 条件 |
|---|---|---|
| `TOBIRA_SPAM_HIGH` | +8.0 | spam_score >= 0.9 |
| `TOBIRA_SPAM_MED` | +5.0 | spam_score >= 0.7 |
| `TOBIRA_SPAM_LOW` | +2.0 | spam_score >= 0.5 |
| `TOBIRA_HAM` | -3.0 | spam_score < 0.3 |
| `TOBIRA_FAIL` | 0.0 | API エラー時（fail-open） |

#### rspamd 設定リファレンス（本番用）

| 設定項目 | デフォルト | 説明 |
|---|---|---|
| `api_url` | `http://127.0.0.1:8000` | API アドレス |
| `timeout` | `2.0` | タイムアウト (秒) |
| `fail_open` | `true` | API エラー時にメールを通すか |
| `send_headers` | `false` | SPF/DKIM/DMARC を送信するか |
| `max_size` | `65536` | 送信するテキストの最大バイト数 |

### Step 3-3: SpamAssassin 経由

SpamAssassin はコンテナ内の `spamc` コマンドでテストします。

```bash
# ham メールをスキャン
echo 'Subject: Meeting tomorrow
From: alice@example.com

Hi Bob, can we meet at 3pm tomorrow?' \
  | docker compose exec -T spamassassin spamc -R
```

出力に `TOBIRA_HAM`（ham 判定時）や `TOBIRA_SPAM_*`（spam 判定時）が含まれていれば tobira プラグインが動作しています。

```bash
# spam メールをスキャン
echo 'Subject: You are a winner!
From: spammer@example.com

Buy now! Free offer! Click here for your lottery winner prize! Act now! Urgent discount casino!' \
  | docker compose exec -T spamassassin spamc -R
```

`TOBIRA_SPAM_HIGH` (8.0 点) が含まれていれば成功です。

```bash
# SpamAssassin ログを確認
docker compose logs spamassassin | grep "tobira:"
```

#### SpamAssassin ルールとタグ

| ルール | スコア | 条件 |
|---|---|---|
| `TOBIRA_SPAM_HIGH` | 8.0 | spam_score >= 0.9 |
| `TOBIRA_SPAM_MED` | 5.0 | spam_score >= 0.7 |
| `TOBIRA_SPAM_LOW` | 2.0 | spam_score >= 0.5 |
| `TOBIRA_HAM` | -3.0 | spam_score < 0.3 |
| `TOBIRA_FAIL` | 0.0 | API エラー時 |

| タグ | 内容 |
|---|---|
| `TOBIRALABEL` | `spam` or `ham` |
| `TOBIRASCORE` | 0.0 〜 1.0 のスコア |

### Step 3-4: Postfix milter（本番向け参考情報）

Docker デモ環境には Postfix milter は含まれていませんが、
本番環境では Postfix と直接統合できます。

```
┌──────────┐  SMTP   ┌──────────┐  milter    ┌──────────────┐  HTTP   ┌─────────────┐
│ 送信元    │───────→│  Postfix  │──────────→│ tobira milter │──────→│  tobira-api │
└──────────┘         └──────────┘            └──────────────┘        └─────────────┘
```

**導入手順（概要）**:

1. `pip install tobira[milter]` でインストール
2. `/etc/tobira/milter.conf` を作成
3. `tobira milter` でデーモン起動（systemd 推奨）
4. Postfix の `smtpd_milters` にソケットを追加

**主な設定項目**:

| 設定 | デフォルト | 説明 |
|---|---|---|
| `api_url` | `http://127.0.0.1:8000` | API アドレス |
| `socket` | `unix:/var/run/tobira/milter.sock` | milter ソケットパス |
| `timeout` | `10` | タイムアウト (秒) |
| `reject_threshold` | `0.9` | reject する閾値（0 で無効） |
| `add_headers` | `true` | X-Tobira-Score/Label ヘッダーを追加 |
| `fail_action` | `accept` | API エラー時の動作 (accept/tempfail) |

> 詳細は `docs/mta/postfix-milter.md` を参照してください。

### Step 3-5: ログをまとめて確認

```bash
# 全サービスのログをリアルタイム表示
docker compose logs -f
```

別のターミナルからメールを送信すると、各サービスのログがリアルタイムで流れます。
`Ctrl+C` で停止。

```bash
# tobira-api に届いたリクエストだけ確認
docker compose logs tobira-api | grep "/v1/predict"
```

### Step 3-6: 自動テストを実行

すべてのサービスの動作を一括検証するテストスクリプトがあります:

```bash
./test.sh
```

すべて PASS になれば、全プラグインの連携が正常に動作しています。

---

## Part 4: Active Learning

不確実性の高いサンプルを優先的に人間にラベル付けしてもらい、
効率的にモデルを改善するワークフローです。

### Step 4-1: キューの確認

```bash
curl -s http://localhost:8000/v1/active-learning/queue | python3 -m json.tool
```

```json
{
    "items": [
        {
            "id": "al-001",
            "text": "Exclusive membership offer just for you - act now!",
            "uncertainty": 0.92,
            "strategy": "entropy",
            "created_at": "2026-03-28T10:00:00Z",
            "label": null
        },
        {
            "id": "al-002",
            "text": "Your invoice #4821 is attached. Please review.",
            "uncertainty": 0.85,
            "strategy": "entropy",
            "created_at": "2026-03-28T10:05:00Z",
            "label": null
        }
    ],
    "total": 3,
    "pending": 3,
    "labeled": 0
}
```

> **ポイント**: `uncertainty` が高い順にソートされています。
> モデルが最も判断に迷ったサンプルから優先的にラベル付けすることで、
> 少ないラベル数で最大の精度改善が得られます。

### Step 4-2: 統計情報の確認

```bash
curl -s http://localhost:8000/v1/active-learning/stats | python3 -m json.tool
```

```json
{
    "total": 3,
    "pending": 3,
    "labeled": 0,
    "strategy": "entropy",
    "avg_uncertainty": 0.85
}
```

> **サンプリング戦略**: entropy（エントロピー）、BALD、margin の 3 種類から選べます。

### Step 4-3: ラベルを付与

```bash
# al-001 を spam としてラベル付け
curl -s -X POST http://localhost:8000/v1/active-learning/label \
  -H 'Content-Type: application/json' \
  -d '{"id": "al-001", "label": "spam"}' \
  | python3 -m json.tool
```

```json
{ "status": "labeled", "id": "al-001", "label": "spam" }
```

```bash
# al-002 を ham としてラベル付け
curl -s -X POST http://localhost:8000/v1/active-learning/label \
  -H 'Content-Type: application/json' \
  -d '{"id": "al-002", "label": "ham"}' \
  | python3 -m json.tool
```

### Step 4-4: ラベル付け後の統計を確認

```bash
curl -s http://localhost:8000/v1/active-learning/stats | python3 -m json.tool
```

`labeled` が 2 に、`pending` が 1 に変わっていれば成功です。

> **本番ワークフロー**:
> 1. `tobira active-learning` CLI で不確実サンプルをキューに投入
> 2. ダッシュボードまたは API でラベル付け
> 3. ラベル付きデータで `tobira train` を実行してモデルを再学習

---

## Part 5: A/B テスト

異なるモデルやバックエンドを同時にテストし、性能を比較できます。

### Step 5-1: A/B テスト結果を確認

```bash
curl -s http://localhost:8000/api/ab-test/results | python3 -m json.tool
```

```json
{
    "variants": {
        "control": {
            "predictions": 3,
            "avg_latency_ms": 12.3,
            "avg_score": 0.42,
            "label_counts": { "spam": 1, "ham": 2 },
            "errors": 0
        },
        "challenger": {
            "predictions": 4,
            "avg_latency_ms": 45.7,
            "avg_score": 0.44,
            "label_counts": { "spam": 2, "ham": 2 },
            "errors": 0
        }
    },
    "started_at": "2026-03-28T10:00:00+00:00",
    "elapsed_seconds": 120.5
}
```

> **ポイント**: predict を何回か実行してから結果を確認すると、
> `predictions` カウントが増えていきます。

### Step 5-2: 予測を増やして比較

```bash
# 何通かのメールを判定
for text in \
  "Meeting at 3pm" \
  "Buy cheap viagra now" \
  "Quarterly report attached" \
  "Free casino bonus click here" \
  "Lunch tomorrow?"; do
  curl -s -X POST http://localhost:8000/v1/predict \
    -H 'Content-Type: application/json' \
    -d "{\"text\": \"$text\"}" > /dev/null
done

# 結果を確認
curl -s http://localhost:8000/api/ab-test/results | python3 -m json.tool
```

> **本番 A/B テスト**: `tobira ab-test` CLI でトラフィック分割方式
> (random / hash-based) や重み付けを設定。精度差に有意性が出たら
> challenger をメインモデルに昇格させます。

---

## Part 6: ダッシュボード

Web ブラウザでモニタリングダッシュボードを確認できます。

```bash
# ブラウザで開く、または curl で確認
curl -s http://localhost:8000/dashboard | head -20
```

ブラウザで http://localhost:8000/dashboard にアクセスすると、
以下の情報がリアルタイムで表示されます:

- **Total Predictions** — 累計予測数
- **Feedback Reports** — フィードバック受信数
- **Active Learning Queue** — ラベル待ちサンプル数

> **本番ダッシュボード**: 予測トレンド、レイテンシグラフ、
> コンセプトドリフト検出、閾値チューニング提案などが表示されます。

---

## Part 7: HA 構成（高可用性）

nginx をリバースプロキシとして、複数の tobira-api インスタンスを
ラウンドロビンで負荷分散する構成を試せます。

### Step 7-1: 既存環境を停止して HA モードで起動

```bash
docker compose down
docker compose -f docker-compose.ha.yml up --build -d
```

### Step 7-2: 動作確認

```bash
# ヘルスチェック（nginx 経由）
curl -s http://localhost:8000/v1/health | python3 -m json.tool

# nginx 自体のヘルスチェック
curl -s http://localhost:8000/nginx-health
```

### Step 7-3: ラウンドロビンの確認

```bash
# 複数回リクエストして、両インスタンスに分散されることを確認
for i in $(seq 1 6); do
  curl -s -X POST http://localhost:8000/v1/predict \
    -H 'Content-Type: application/json' \
    -d '{"text": "Test message"}' > /dev/null
  echo "Request $i sent"
done

# 各インスタンスのログでリクエスト数を確認
docker compose -f docker-compose.ha.yml logs tobira-api-1 | grep -c "/v1/predict"
docker compose -f docker-compose.ha.yml logs tobira-api-2 | grep -c "/v1/predict"
```

両インスタンスにほぼ均等にリクエストが分散されていれば成功です。

### Step 7-4: フェイルオーバーの確認

```bash
# インスタンス 1 を停止
docker compose -f docker-compose.ha.yml stop tobira-api-1

# リクエストは引き続き成功する（インスタンス 2 にフォールバック）
curl -s http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "Test after failover"}' | python3 -m json.tool

# インスタンス 1 を復旧
docker compose -f docker-compose.ha.yml start tobira-api-1
```

> **HA 構成のポイント**:
> - 各インスタンスにリソース制限（1 CPU, 512MB）が設定済み
> - `restart: unless-stopped` で自動復旧
> - nginx は `max_fails=3 fail_timeout=10s` で障害検知
> - `proxy_next_upstream` で接続失敗時に自動的に次のサーバーへ

```bash
# HA モードを停止して通常モードに戻す
docker compose -f docker-compose.ha.yml down
docker compose up --build -d
```

---

## Part 8: 設定ファイルリファレンス

tobira は TOML 形式の設定ファイルで細かく制御できます。
以下は全セクションの例です。

```toml
# === バックエンド設定 ===
[backend]
# 選択肢: fasttext, bert, onnx, ollama, llm_api, ensemble, two_stage
type = "ollama"
model = "gemma2:2b"
base_url = "http://localhost:11434"
timeout = 30

# --- FastText の場合 ---
# [backend]
# type = "fasttext"
# model_path = "/path/to/model.bin"

# --- ONNX の場合 ---
# [backend]
# type = "onnx"
# model_path = "/path/to/model.onnx"
# quantized = true

# --- BERT/DeBERTa の場合 ---
# [backend]
# type = "bert"
# model_path = "microsoft/mdeberta-v3-base"
# device = "cuda"     # or "cpu"

# --- Ensemble (複数バックエンド組み合わせ) ---
# [backend]
# type = "ensemble"
# method = "weighted_average"  # or "majority_vote"
# [[backend.members]]
# type = "fasttext"
# model_path = "/path/to/fasttext.bin"
# weight = 0.3
# [[backend.members]]
# type = "onnx"
# model_path = "/path/to/model.onnx"
# weight = 0.7

# --- Two-Stage (高速フィルタ + 高精度モデル) ---
# [backend]
# type = "two_stage"
# [backend.first_stage]
# type = "fasttext"
# model_path = "/path/to/fasttext.bin"
# [backend.second_stage]
# type = "onnx"
# model_path = "/path/to/model.onnx"
# grey_zone_low = 0.3
# grey_zone_high = 0.7

# === モニタリング ===
[monitoring]
enabled = true
store_type = "jsonl"     # or "redis"
log_path = "/var/log/tobira/predictions.jsonl"

# [monitoring.redis]
# url = "redis://localhost:6379"
# prefix = "tobira:"

# === フィードバック収集 ===
[feedback]
enabled = true
store_path = "/var/log/tobira/feedback.jsonl"

# === ヘッダー分析 ===
[header_analysis]
enabled = false   # true にすると SPF/DKIM/DMARC スコアを加味

# === ダッシュボード ===
[dashboard]
enabled = false   # true にすると /dashboard エンドポイントが有効

# === AI 生成テキスト検出 ===
[ai_detection]
enabled = false   # true にすると ai_generated フィールドを返却
```

> **環境変数オーバーライド**: すべての設定は `TOBIRA_` プレフィクスの
> 環境変数で上書きできます（例: `TOBIRA_BACKEND_TYPE=fasttext`）。

### バックエンド比較表

| バックエンド | モデルサイズ | レイテンシ | ハードウェア | 精度 |
|---|---|---|---|---|
| FastText | ~10MB | ~1ms | CPU | 中 |
| ONNX | ~110MB (量子化) | ~30ms | CPU | 高 |
| BERT/DeBERTa | 340-440MB | ~200ms | GPU 推奨 | 高 |
| Ollama | 1-70GB | ~500ms (GPU) | GPU 推奨 | 高 |
| LLM API | リモート | ~300ms | 不要 | 最高 |
| Ensemble | 構成次第 | 構成次第 | 構成次第 | 最高 |
| Two-Stage | 小+中 | 1-30ms | CPU | 高 |

> **推奨**: まず FastText or ONNX で始め、精度が足りなければ
> Ensemble or Two-Stage にアップグレード。
> DeBERTa-v3 は旧 BERT より高精度で推奨されています。

---

## Part 9: CLI コマンド概要

`pip install tobira` でインストールした場合に使える CLI コマンドの一覧です。

| コマンド | 説明 |
|---|---|
| `tobira init` | MTA を自動検出して設定ファイルを生成 |
| `tobira serve` | API サーバーを起動 |
| `tobira doctor` | 設定・モデル・接続を一括診断 |
| `tobira demo` | Docker Compose デモ環境を起動 |
| `tobira train` | ラベル付きデータで BERT/DeBERTa をファインチューン |
| `tobira evaluate` | テストデータでモデルを評価（精度・再現率・F1・混同行列） |
| `tobira monitor` | 予測メトリクスを分析（ドリフト検出・閾値チューニング） |
| `tobira distill` | 知識蒸留（大モデル→小モデルへの圧縮） |
| `tobira ab-test` | A/B テストの設定と管理 |
| `tobira active-learning` | Active Learning キューの管理 |
| `tobira hub-push` | HuggingFace Hub にモデルをアップロード |
| `tobira hub-pull` | HuggingFace Hub からモデルをダウンロード |
| `tobira milter` | Postfix milter デーモンを起動 |

### 主要コマンドの使用例

```bash
# 初期セットアップ（MTA 自動検出 + 設定ファイル生成）
tobira init

# 診断の実行
tobira doctor

# FastText バックエンドでサーバー起動
tobira serve --backend fasttext --model-path /path/to/model.bin

# TOML 設定ファイルを指定して起動
tobira serve --config /etc/tobira/config.toml --host 0.0.0.0 --port 8000

# モデルの学習
tobira train --data /path/to/labeled.csv --output /path/to/model/

# モデルの評価
tobira evaluate --backend bert --model-path /path/to/model/ --test-data /path/to/test.csv

# モニタリング（デーモンモード: 5分間隔で自動チェック）
tobira monitor --daemon --interval 300

# 知識蒸留（大モデル → 小モデル）
tobira distill --teacher bert --teacher-path /path/to/large/ \
               --student fasttext --output /path/to/small.bin

# HuggingFace Hub との連携
tobira hub-push --model-path /path/to/model/ --repo your-org/tobira-model
tobira hub-pull --repo your-org/tobira-model --output /path/to/model/
```

---

## Part 10: 本番ロールアウト戦略

tobira を本番環境に導入する際の推奨 4 フェーズです。

### Phase A: 既存フィルタで運用（データ収集）

```
メール → [Postfix/rspamd] → 既存ルールで判定
                ↓
         ログ収集（学習データとして蓄積）
```

- 既存の spam フィルタはそのまま運用
- tobira は **観測モードのみ**（reject しない）
- `[monitoring]` を有効にして予測ログを収集

### Phase B: モデル学習

```bash
# 収集データで学習
tobira train --data /path/to/collected.csv --output /path/to/model/

# 評価（F1 >= 0.95 を品質ゲートに）
tobira evaluate --test-data /path/to/test.csv --model-path /path/to/model/
```

### Phase C: 段階的デプロイ

1. **観測モード** — tobira の判定結果をヘッダーに追加するだけ（reject しない）
2. **部分適用** — 特定ドメインや一部トラフィックのみ tobira で reject
3. **全面適用** — 全トラフィックに適用

> A/B テスト機能を使って、既存フィルタと tobira の精度を並行比較できます。

### Phase D: 継続的モニタリング

```bash
# コンセプトドリフト検出（スコア分布の変化を PSI/KS テストで検出）
tobira monitor --daemon --interval 300
```

- スコア分布の変化を検出したら再学習
- フィードバック API で誤分類レポートを収集
- Active Learning で効率的にラベル付け

---

## クリーンアップ

```bash
# mock モード
docker compose down

# real モード
docker compose -f docker-compose.real.yml down

# HA モード
docker compose -f docker-compose.ha.yml down
```

ビルドキャッシュも含めて完全に削除する場合:

```bash
# mock モード
docker compose down --rmi local --volumes

# real モード（Ollama のモデルキャッシュも削除）
docker compose -f docker-compose.real.yml down --rmi local --volumes
```

---

## トラブルシューティング

### サービスが起動しない

```bash
docker compose logs tobira-api
docker compose logs haraka
docker compose logs rspamd
docker compose logs spamassassin

# real モードの場合
docker compose -f docker-compose.real.yml logs ollama
docker compose -f docker-compose.real.yml logs ollama-init
```

### real モードで tobira-api が起動しない

Ollama のモデルダウンロードが完了しているか確認:

```bash
docker compose -f docker-compose.real.yml logs ollama-init
```

`success` と表示されていれば OK。タイムアウトした場合は再実行:

```bash
docker compose -f docker-compose.real.yml restart ollama-init
```

### real モードで predict が遅い

初回リクエストは LLM のウォームアップのため数秒かかります。
2 回目以降は高速化されます。GPU が利用可能な環境では
Ollama が自動的に GPU を使用します。

### rspamd の TOBIRA シンボルが出ない

rspamd は起動直後にプラグインのロードに数秒かかることがあります。
10 秒ほど待ってから再度スキャンしてください。

### ポートが競合する

他のサービスが 8000, 2525, 11333, 11334, 783 を使用している場合、
compose ファイルの `ports` を変更:

```yaml
ports:
  - "18000:8000"  # 例: ホスト側を 18000 に変更
```

### API エンドポイントが 404 になる

mock サーバーを再ビルドしてください:

```bash
docker compose down
docker compose up --build -d
```

### HA モードで nginx が起動しない

両方の API インスタンスが healthy になるまで nginx は起動しません:

```bash
docker compose -f docker-compose.ha.yml logs tobira-api-1
docker compose -f docker-compose.ha.yml logs tobira-api-2
```
