# Discord翻訳Bot

Gemini APIによるテキスト翻訳と、Edge TTSによる音声合成を組み合わせたDiscord向け翻訳Botです。

Discord上で受信したメッセージを翻訳し、翻訳結果を音声としてボイスチャンネルで再生します。

## 機能

* Discordメッセージの翻訳
* Gemini APIによる翻訳
* Edge TTSによる音声合成
* Discordボイスチャンネルでの音声再生
* 日本語・英語・韓国語の音声設定
* サーバー（Guild）ごとの設定管理
* 非同期キューによる音声再生処理
* Dockerによるコンテナ実行
* pytestによる自動テスト
* RuffによるLint / Formatチェック
* GitHub ActionsによるCI

## システム構成

```text id="715fci"
Discord
   │
   │ メッセージ
   ▼
Python Discord Bot
   │
   ├── Gemini API
   │      └── 翻訳
   │
   ├── 非同期キュー
   │      └── サーバーごとの音声処理
   │
   └── Edge TTS
          └── 音声合成
                 │
                 ▼
          Discordボイスチャンネル
```

## 使用技術

| 分類            | 技術                      |
| ------------- | ----------------------- |
| 言語            | Python 3.11             |
| Discord       | discord.py              |
| 翻訳            | Gemini API              |
| 音声合成          | Edge TTS                |
| 音声処理          | FFmpeg                  |
| コンテナ          | Docker / Docker Compose |
| テスト           | pytest / pytest-asyncio |
| Lint / Format | Ruff                    |
| CI            | GitHub Actions          |

## ディレクトリ構成

```text id="x75et7"
.
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   ├── audio_queue.py
│   ├── bot.py
│   ├── config.py
│   └── translator.py
├── tests/
│   ├── test_audio_queue.py
│   ├── test_config.py
│   └── test_translator.py
├── Dockerfile
├── docker-compose.yaml
├── main.py
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

## セットアップ

### 1. リポジトリをClone

```bash id="4gt3na"
git clone https://github.com/segawa74/discord-translation-bot.git
cd discord-translation-bot
```

### 2. 環境変数を設定

`.env.example` をコピーします。

```bash id="amqwn3"
cp .env.example .env
```

`.env` に以下を設定します。

```env id="69ey1e"
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
```

`.env` はGitにコミットしないでください。

### 3. Docker Composeで起動

```bash id="jeim34"
docker compose up --build
```

BotがDiscordに接続すると起動完了です。

停止する場合：

```bash id="1cndw7"
docker compose down
```

## 開発

開発用依存関係をインストールします。

```bash id="m0sw0h"
pip install -r requirements-dev.txt
```

### テスト

```bash id="p6qfyg"
pytest
```

### Ruff

Lintチェック：

```bash id="lqr67y"
ruff check .
```

フォーマットチェック：

```bash
ruff format --check .
```

## CI

GitHub Actionsを利用し、コードをPushした際に自動でテストおよびコード品質チェックを実行します。

現在のCIでは以下を確認します。

* pytestによるテスト
* RuffによるLintチェック
* Ruffによるフォーマットチェック

これにより、コード変更による既存機能の破壊やコード品質上の問題を早期に検出できるようにしています。

## 設計上のポイント

### 非同期キューによる音声処理

音声再生には非同期キューを使用しています。

サーバー（Guild）ごとにキューとワーカーを用意し、複数のサーバーで音声処理を行っても、Discord Botのイベントループを不必要にブロックしない構成としています。

### 一時音声ファイル

Edge TTSで生成した音声を一時ファイルとして保存し、FFmpegを利用してDiscordのボイスチャンネルへ再生します。

複数のメッセージを処理する際にファイル名が衝突しないよう、メッセージごとに一意なファイル名を使用しています。

### エラーハンドリング

翻訳、音声合成、音声再生などの処理でエラーが発生した場合でも、Bot全体が停止しないようにエラーを処理しています。

## 今後の改善予定

* AWSへのデプロイによる常時稼働
* 設定情報の永続化
* 翻訳時の文脈保持
* 対応言語・音声の追加
* 結合テストの拡充
* ログ・監視機能の強化
* 音声キューのキャンセル・優先度制御

## ライセンス

個人開発・ポートフォリオ用途を想定しています。
