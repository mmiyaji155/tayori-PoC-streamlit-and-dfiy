# API キー設定手順

## 必要なAPI キー

### 1. OpenAI API Key
1. [OpenAI Platform](https://platform.openai.com/) にログイン
2. 左メニューから「API Keys」をクリック
3. 「Create new secret key」でAPI キーを生成
4. `sk-` で始まるキーをコピー

### 2. Dify API Key & App ID
1. [Dify](https://cloud.dify.ai/) にログイン
2. 新規Chatflowアプリを作成
3. 「App Settings」→「API Key」に移動
4. API Keyを生成（`app-` で始まる）
5. App IDを確認

## ローカル設定

`.streamlit/secrets.toml` ファイルを編集して、実際のAPI キーを設定してください：

```toml
[general]
OPENAI_API_KEY = "sk-実際のOpenAIキー"
DIFY_API_KEY = "app-実際のDifyキー"  
DIFY_APP_ID = "実際のDifyアプリID"
```

⚠️ **重要**: このファイルは .gitignore で除外されており、GitHubには送信されません。

## 本番環境設定（Streamlit Community Cloud）

1. GitHubにプッシュ
2. [Streamlit Community Cloud](https://share.streamlit.io) でアプリを作成
3. Settings → Secrets でAPI キーを設定

```
OPENAI_API_KEY = "sk-..."
DIFY_API_KEY = "app-..."
DIFY_APP_ID = "xxxxxxxx"
```
