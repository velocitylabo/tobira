# FastText バックエンドで tobira を動かすハンズオン（Docker 版）

FastText モデルを学習し、tobira の API サーバーで実際にスパム分類を行う **学習用ハンズオン** です。
Docker を使うためローカル環境を汚しません。

> **これは何？**: FastText バックエンドの仕組みを理解するための教材です。
> 「とにかく素早く動かしたい」場合は [`docker-compose.fasttext.yml`](../../docker/docker-compose.fasttext.yml) で
> `docker compose up` 一発で起動できます。

> **所要時間**: 約 20〜30 分

## 目次

- [Part 1: 前提条件](#part-1-前提条件)
- [Part 2: コンテナの準備](#part-2-コンテナの準備)
- [Part 3: 学習データの準備](#part-3-学習データの準備)
- [Part 4: FastText モデルの学習](#part-4-fasttext-モデルの学習)
- [Part 5: tobira サーバーで FastText を使う](#part-5-tobira-サーバーで-fasttext-を使う)
- [Part 6: Two-Stage バックエンド（応用）](#part-6-two-stage-バックエンド応用)
- [クリーンアップ](#クリーンアップ)
- [トラブルシューティング](#トラブルシューティング)

---

## Part 1: 前提条件

### 必要な環境

- Docker

### Part 6 のみ追加で必要

- Ollama（ホスト側にインストール済みであること）
- `gemma2:2b` モデル（`ollama pull gemma2:2b`）

---

## Part 2: コンテナの準備

### コンテナの起動

リポジトリのルートディレクトリで実行してください。

```bash
docker run -it --rm \
  --name tobira-fasttext \
  --network host \
  -v "$(pwd)":/workspace \
  -w /workspace/docs/handson \
  python:3.12-slim \
  bash
```

> **Note**: `--network host` は Part 6 (Two-Stage) で Ollama に接続するために必要です。
> Part 5 までしか試さない場合は省略できます。

以降のコマンドはすべてコンテナ内で実行します。

### tobira のインストール

```bash
pip install /workspace/python[serving,fasttext]
```

### 動作確認

```bash
# FastText が使えることを確認
python3 -c "import fasttext; print('fasttext OK')"

# tobira CLI が使えることを確認
tobira --help
```

---

## Part 3: 学習データの準備

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

## Part 4: FastText モデルの学習

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

NumPy 2.x 環境で `fasttext` を直接使うとエラーが出るため、
NumPy 1.x をインストールしてから検証します。

```bash
pip install "numpy<2"
```

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

NumPy 2.x に戻します（tobira サーバーには互換パッチがあるため 2.x で問題ありません）。

```bash
pip install "numpy>=2"
```

### モデルサイズの確認

```bash
ls -lh fasttext-spam.bin
```

50 件の学習データでは数百 MB 程度になることがあります（FastText のデフォルト設定による文字 n-gram のため）。
本番用のデータ（数万件〜）で学習する場合は `dim` パラメータの調整を検討してください。

---

## Part 5: tobira サーバーで FastText を使う

### 設定ファイルの作成

```bash
cat > tobira.toml << 'EOF'
[backend]
type = "fasttext"
model_path = "./fasttext-spam.bin"
EOF
```

### サーバーの起動

バックグラウンドで起動します。

```bash
tobira serve --config tobira.toml &
sleep 3
```

### ヘルスチェック

```bash
python3 -c "
import urllib.request, json
r = urllib.request.urlopen('http://127.0.0.1:8000/v1/health')
print(json.dumps(json.loads(r.read()), indent=2))
"
```

```json
{
  "status": "ok"
}
```

### ham メールを分類

```bash
python3 -c "
import urllib.request, json
data = json.dumps({'text': 'Hi Bob, can we meet at 3pm tomorrow to discuss the project?'}).encode()
req = urllib.request.Request('http://127.0.0.1:8000/v1/predict', data=data, headers={'Content-Type': 'application/json'})
r = urllib.request.urlopen(req)
print(json.dumps(json.loads(r.read()), indent=2, ensure_ascii=False))
"
```

期待される出力（`label` が `ham`、`score` が高い）:

```json
{
  "label": "ham",
  "score": 0.95,
  "labels": {
    "ham": 0.95,
    "spam": 0.05
  }
}
```

### spam メールを分類

```bash
python3 -c "
import urllib.request, json
data = json.dumps({'text': 'Congratulations! You won a free iPhone! Click here to claim now!'}).encode()
req = urllib.request.Request('http://127.0.0.1:8000/v1/predict', data=data, headers={'Content-Type': 'application/json'})
r = urllib.request.urlopen(req)
print(json.dumps(json.loads(r.read()), indent=2, ensure_ascii=False))
"
```

期待される出力（`label` が `spam`、`score` が高い）:

```json
{
  "label": "spam",
  "score": 0.98,
  "labels": {
    "spam": 0.98,
    "ham": 0.02
  }
}
```

### 日本語メールを分類

```bash
python3 -c "
import urllib.request, json
data = json.dumps({'text': '今すぐクリック！100万円が当たるチャンス！無料登録はこちら！'}).encode()
req = urllib.request.Request('http://127.0.0.1:8000/v1/predict', data=data, headers={'Content-Type': 'application/json'})
r = urllib.request.urlopen(req)
print(json.dumps(json.loads(r.read()), indent=2, ensure_ascii=False))
"
```

> **Note**: スコアの精度は学習データの量と質に依存します。
> 50 件のサンプルデータでは、一部のメールで誤分類が起こる可能性があります。

サーバーを停止します。

```bash
kill %1
```

---

## Part 6: Two-Stage バックエンド（応用）

FastText を高速な第 1 段フィルタとして使い、判定が微妙なメールだけを
高精度な第 2 段バックエンド（Ollama）に送る構成です。

> **前提**: ホスト側で Ollama が起動済みで、`gemma2:2b` モデルがダウンロード済みであること。
>
> ```bash
> # ホスト側で実行
> ollama serve    # 別ターミナルで起動しておく
> ollama pull gemma2:2b
> ```

### アーキテクチャ

```
メール → [FastText ~1ms]
              │
         確信度高い → 即判定（ham or spam）  ← 80〜90% のメール
              │
         グレーゾーン → [Ollama ~500ms] → 精密判定  ← 10〜20% のメール
```

### Ollama への疎通確認

コンテナ起動時に `--network host` を指定していれば、ホストの Ollama にアクセスできます。

```bash
python3 -c "
import urllib.request, json
r = urllib.request.urlopen('http://localhost:11434/api/tags')
models = json.loads(r.read())
print(json.dumps(models, indent=2))
"
```

### LLM 依存のインストール

```bash
pip install /workspace/python[llm]
```

### 設定ファイルの作成

```bash
cat > tobira-twostage.toml << 'EOF'
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
EOF
```

### grey_zone パラメータ

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `low` | `0.3` | これ以下のスコアは ham として即判定 |
| `high` | `0.7` | これ以上のスコアは spam として即判定 |

`low` と `high` の間（グレーゾーン）のメールだけが第 2 段に送られるため、
高精度バックエンドの負荷を大幅に削減できます。

### サーバーの起動

```bash
tobira serve --config tobira-twostage.toml &
sleep 5
```

### テスト

```bash
python3 -c "
import urllib.request, json

def predict(text, label=''):
    data = json.dumps({'text': text}).encode()
    req = urllib.request.Request('http://127.0.0.1:8000/v1/predict', data=data, headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=60)
    result = json.loads(r.read())
    print(f'[{label}]')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()

# 明確な ham（FastText で即判定されるはず）
predict('Hi Bob, can we meet at 3pm tomorrow to discuss the project?', 'ham')

# 明確な spam（FastText で即判定されるはず）
predict('Congratulations! You won a free iPhone! Click here to claim now!', 'spam')

# 日本語 spam
predict('今すぐクリック！100万円が当たるチャンス！無料登録はこちら！', '日本語 spam')
"
```

サーバーを停止します。

```bash
kill %1
```

---

## クリーンアップ

コンテナ内で作成したファイルを削除してからコンテナを終了します。

```bash
rm -f train.txt fasttext-spam.bin tobira.toml tobira-twostage.toml
exit
```

`docker run` に `--rm` を付けて起動しているため、`exit` でコンテナは自動削除されます。
ホスト環境には一切影響ありません。

---

## トラブルシューティング

### NumPy 2.x で `ValueError: Unable to avoid copy while creating an array`

`fasttext` を直接使う場合に発生します。NumPy を 1.x にダウングレードしてください:

```bash
pip install "numpy<2"
```

tobira の FastText バックエンドには互換パッチが含まれているため、
`tobira serve` 経由で使う場合は問題ありません。

### Ollama に接続できない（Part 6）

コンテナ起動時に `--network host` を指定しているか確認してください:

```bash
# コンテナ内から確認
python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags'); print('OK')"
```

接続できない場合はホスト側で Ollama が起動していることを確認してください。

### モデルの精度が低い

50 件のサンプルデータはデモ用です。本番では:

- 数千〜数万件の学習データを用意
- `epoch=25, lr=1.0, wordNgrams=2` を調整
- `tobira evaluate` で精度を測定（→ [CLI ハンズオン](cli.md) Part 7）
