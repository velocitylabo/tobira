# FastText バックエンドで tobira を動かすハンズオン

FastText モデルを学習し、tobira の API サーバーで実際にスパム分類を行う **学習用ハンズオン** です。
Docker は不要で、Python 環境のみで完結します。

> **これは何？**: FastText バックエンドの仕組みを理解するための教材です。
> 「とにかく素早く動かしたい」場合は [`docker-compose.fasttext.yml`](../../docker/docker-compose.fasttext.yml) で
> `docker compose up` 一発で起動できます。

> **所要時間**: 約 20〜30 分

## 目次

- [Part 1: 前提条件とインストール](#part-1-前提条件とインストール)
- [Part 2: 学習データの準備](#part-2-学習データの準備)
- [Part 3: FastText モデルの学習](#part-3-fasttext-モデルの学習)
- [Part 4: tobira サーバーで FastText を使う](#part-4-tobira-サーバーで-fasttext-を使う)
- [Part 5: Two-Stage バックエンド（応用）](#part-5-two-stage-バックエンド応用)
- [クリーンアップ](#クリーンアップ)
- [トラブルシューティング](#トラブルシューティング)

---

## Part 1: 前提条件とインストール

### 必要な環境

- Python 3.9+

### インストール

```bash
pip install tobira[serving,fasttext]
```

### 動作確認

```bash
# FastText が使えることを確認
python3 -c "import fasttext; print('fasttext OK')"

# tobira CLI が使えることを確認
tobira --help
```

---

## Part 2: 学習データの準備

FastText の教師あり学習には、ラベル付きテキストデータが必要です。

### サンプルデータ

本リポジトリに含まれる `sample_train.csv` を使用します（50 件: spam 25 件 + ham 25 件）。

```bash
# データの確認
head -5 sample_train.csv
```

```
text,label
"Hi team, the quarterly review meeting is scheduled for Friday at 2pm.",ham
"Please find attached the invoice for March services.",ham
...
```

### FastText 形式への変換

FastText は `__label__ラベル名 テキスト` という独自形式を使います。
CSV から変換するスクリプトを実行します。

```bash
python3 -c "
import csv
with open('sample_train.csv') as f, open('train.txt', 'w') as out:
    for row in csv.DictReader(f):
        out.write(f'__label__{row[\"label\"]} {row[\"text\"]}\n')
print('train.txt を作成しました')
"
```

変換結果を確認:

```bash
head -3 train.txt
```

```
__label__ham Hi team, the quarterly review meeting is scheduled for Friday at 2pm.
__label__ham Please find attached the invoice for March services.
__label__ham Can we reschedule the 1-on-1 to Thursday afternoon?
```

---

## Part 3: FastText モデルの学習

### モデルの学習

```bash
python3 -c "
import fasttext

model = fasttext.train_supervised(
    'train.txt',
    epoch=25,
    lr=1.0,
    wordNgrams=2,
)
model.save_model('fasttext-spam.bin')
print('モデルを fasttext-spam.bin に保存しました')
"
```

> 50 件のデータなら 1 秒もかかりません。

### モデルの検証

```bash
python3 -c "
import fasttext

model = fasttext.load_model('fasttext-spam.bin')

# ham メールをテスト
result = model.predict('Hi, can we schedule our weekly meeting?')
print(f'ham テスト: {result}')

# spam メールをテスト
result = model.predict('Buy cheap medicine now! Free offer! Click here!')
print(f'spam テスト: {result}')
"
```

期待される出力:

```
ham テスト: (('__label__ham',), array([...]))
spam テスト: (('__label__spam',), array([...]))
```

### モデルサイズの確認

```bash
ls -lh fasttext-spam.bin
```

50 件の学習データでは数十 KB 程度です。
本番用のデータ（数万件〜）で学習すると 5〜30 MB 程度になります。

---

## Part 4: tobira サーバーで FastText を使う

### 設定ファイルの作成

```bash
cat > tobira.toml << 'EOF'
[backend]
type = "fasttext"
model_path = "./fasttext-spam.bin"
EOF
```

### サーバーの起動

```bash
tobira serve --config tobira.toml
```

別のターミナルを開いて、以下のコマンドを実行します。

### ヘルスチェック

```bash
curl -s http://127.0.0.1:8000/v1/health | python3 -m json.tool
```

```json
{
    "status": "ok"
}
```

### ham メールを分類

```bash
curl -s -X POST http://127.0.0.1:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hi Bob, can we meet at 3pm tomorrow to discuss the project?"}' \
  | python3 -m json.tool
```

期待される出力（`label` が `ham`、`score` が高い）:

```json
{
    "label": "ham",
    "score": 0.95,
    "labels": {
        "ham": 0.95,
        "spam": 0.05
    },
    "model_version": "unknown"
}
```

### spam メールを分類

```bash
curl -s -X POST http://127.0.0.1:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "Congratulations! You won a free iPhone! Click here to claim now!"}' \
  | python3 -m json.tool
```

期待される出力（`label` が `spam`、`score` が高い）:

```json
{
    "label": "spam",
    "score": 0.98,
    "labels": {
        "spam": 0.98,
        "ham": 0.02
    },
    "model_version": "unknown"
}
```

### 日本語メールを分類

```bash
curl -s -X POST http://127.0.0.1:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "今すぐクリック！100万円が当たるチャンス！無料登録はこちら！"}' \
  | python3 -m json.tool
```

> **Note**: スコアの精度は学習データの量と質に依存します。
> 50 件のサンプルデータでは、一部のメールで誤分類が起こる可能性があります。

サーバーを停止するには、起動したターミナルで `Ctrl+C` を押します。

---

## Part 5: Two-Stage バックエンド（応用）

FastText を高速な第 1 段フィルタとして使い、判定が微妙なメールだけを
高精度な第 2 段バックエンド（Ollama 等）に送る構成です。

### アーキテクチャ

```
メール → [FastText ~1ms]
              │
         確信度高い → 即判定（ham or spam）  ← 80〜90% のメール
              │
         グレーゾーン → [Ollama ~500ms] → 精密判定  ← 10〜20% のメール
```

### 設定例

```toml
[backend]
type = "two_stage"

[backend.first_stage]
type = "fasttext"
model_path = "./fasttext-spam.bin"

[backend.second_stage]
type = "ollama"
model = "gemma2:2b"
base_url = "http://localhost:11434"

[backend.grey_zone]
low = 0.3    # spam スコアがこれ以下 → ham 確定
high = 0.7   # spam スコアがこれ以上 → spam 確定
             # 0.3〜0.7 の間 → 第 2 段に送る
```

> **Note**: この構成には Ollama が必要です（`ollama serve` で起動し、
> `ollama pull gemma2:2b` でモデルをダウンロード）。
> Ollama がない場合はこのパートをスキップしてください。

### grey_zone パラメータ

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `low` | `0.3` | これ以下のスコアは ham として即判定 |
| `high` | `0.7` | これ以上のスコアは spam として即判定 |

`low` と `high` の間（グレーゾーン）のメールだけが第 2 段に送られるため、
高精度バックエンドの負荷を大幅に削減できます。

---

## クリーンアップ

```bash
rm -f train.txt fasttext-spam.bin tobira.toml
```

---

## トラブルシューティング

### `ModuleNotFoundError: No module named 'fasttext'`

```bash
pip install fasttext-wheel>=0.9.2
```

### NumPy 2.x で `TypeError: __array__() takes 1 positional argument`

tobira の FastText バックエンドには互換パッチが含まれているため、
`tobira serve` 経由で使う場合は問題ありません。
`fasttext` を直接使う場合は NumPy を 1.x にダウングレードしてください:

```bash
pip install "numpy<2"
```

### モデルの精度が低い

50 件のサンプルデータはデモ用です。本番では:

- 数千〜数万件の学習データを用意
- `epoch=25, lr=1.0, wordNgrams=2` を調整
- `tobira evaluate` で精度を測定（→ [CLI ハンズオン](cli.md) Part 7）
