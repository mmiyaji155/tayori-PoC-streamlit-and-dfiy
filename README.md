# Streamlit × Dify ハイブリッド音声要約チャットシステム

音声ファイルをアップロードすると、OpenAI Whisper API で文字起こしを行い、Dify Chatflow で要約を生成するStreamlitアプリケーションです。

## 機能

- 🎤 **音声ファイルアップロード**: 大容量ファイル対応（自動圧縮機能付き）
- 🗜️ **自動圧縮**: 25MB超過時は自動でWhisper API制限内に圧縮
- 📝 **自動文字起こし**: OpenAI Whisper API による高精度な文字起こし
- ✨ **シンプル処理**: アップロードして実行するだけ
- 📊 **AI要約**: Dify Chatflow による要約生成
- 💬 **チャットUI**: 直感的なチャットインターフェース

## 対応音声形式

m4a, mp3, wav, flac, mp4, mpeg, mpga, oga, ogg, webm

## セットアップ

### 1. 環境構築

```bash
# 仮想環境作成
python -m venv .venv

# 仮想環境有効化 (Windows)
.venv\Scripts\activate

# 依存ライブラリインストール
pip install -r requirements.txt
```

### 2. API キー設定

Streamlit Secrets に以下のキーを設定：

```toml
OPENAI_API_KEY = "sk-..."
DIFY_API_KEY = "app-..."
DIFY_APP_ID = "xxxxxxxx"
```

### 3. Dify Chatflow 設定

1. Dify で新規 Chatflow アプリを作成
2. ノード構成:
   - Start ノード
   - LLM ノード (GPT-4o-mini推奨)
   - End ノード
3. API キーを発行

## 実行

```bash
streamlit run app.py
```

## デプロイ (Streamlit Community Cloud)

1. GitHub にプッシュ
2. [Streamlit Community Cloud](https://share.streamlit.io) でデプロイ
3. Secrets 設定でAPI キーを登録

## システム構成

```
User → Streamlit UI → OpenAI Whisper API
                  ↓
              Dify Chatflow → GPT-4o-mini
```

## 技術スタック

- **フロントエンド**: Streamlit 1.36+
- **音声処理**: OpenAI Whisper API
- **要約生成**: Dify Chatflow + GPT-4o-mini
- **デプロイ**: Streamlit Community Cloud
