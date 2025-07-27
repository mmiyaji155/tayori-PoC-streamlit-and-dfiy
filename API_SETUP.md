# API キー設定手順

## 🔑 必要なAPI キー

### 1. OpenAI API Key
**用途**: Whisper API による音声文字起こし

1. [OpenAI Platform](https://platform.openai.com/) にログイン
2. 左メニューから「API Keys」をクリック
3. 「Create new secret key」でAPI キーを生成
4. `sk-` で始まるキーをコピー

💡 **注意**: 従量課金制のため、事前にクレジットカードの登録が必要です

### 2. Dify API Key
**用途**: Chatflow による要約生成と継続会話

1. [Dify Cloud](https://cloud.dify.ai/) にログイン
2. 新規**Chatflow**アプリを作成
3. 「発行」→「API Access」に移動
4. API Keyを生成（`app-` で始まる）

## 🛠️ Dify Chatflow 設定

### 基本構成
```
Start ノード → LLM ノード → End ノード
```

### LLM ノード設定
- **モデル**: GPT-4o-mini（推奨）または GPT-4o
- **System Prompt 例**:
```
あなたは優秀な要約アシスタントです。

以下のルールに従って文字起こしテキストを要約してください：
1. 重要なポイントを5つの箇条書きで整理
2. 各ポイントは具体的で分かりやすく記述
3. 専門用語がある場合は簡潔な説明を併記
4. 話者の感情や意図も可能な限り反映
5. 文字数は300-500字程度に収める

追加の質問や修正指示があった場合は、この要約内容を基に回答してください。
```

- **入力変数**: `{{#start.text}}`
- **出力変数**: `answer`

### 詳細設定のコツ
- **Temperature**: 0.3-0.5（一貫性重視）
- **Max Tokens**: 1000-2000（十分な応答長さ確保）
- **会話履歴**: 有効化（継続会話のため）

## 💻 ローカル設定

`.streamlit/secrets.toml` ファイルを作成：

```toml
OPENAI_API_KEY = "sk-proj-xxxxxxxxxx"
DIFY_API_KEY = "app-xxxxxxxxxx"
```

⚠️ **重要**: 
- このファイルは .gitignore で除外されており、GitHubには送信されません
- 実際のキーに置き換えてください
- ファイルの拡張子は `.toml` です

## 🌐 本番環境設定（Streamlit Community Cloud）

### デプロイ手順
1. GitHubにコードをプッシュ
2. [Streamlit Community Cloud](https://share.streamlit.io) でアプリを作成
3. **Settings** → **Secrets** でAPI キーを設定

### Secrets設定
```toml
OPENAI_API_KEY = "sk-proj-xxxxxxxxxx"
DIFY_API_KEY = "app-xxxxxxxxxx"
```

## 🧪 動作確認

### 1. API キー疎通確認
アプリを起動すると、API キーが正しく設定されているかチェックされます。
エラーが表示される場合は、キーの設定を見直してください。

### 2. 機能テスト
1. **音声アップロード**: 短い音声ファイル（1-2分）でテスト
2. **文字起こし**: Whisper API が正常に動作するか確認
3. **要約生成**: Dify が適切な要約を返すか確認
4. **継続会話**: 要約について質問して回答が得られるか確認

## 🔧 トラブルシューティング

### よくあるエラー

**`Secrets に OPENAI_API_KEY がありません`**
- `.streamlit/secrets.toml` ファイルが存在するか確認
- ファイル内のキー名が正確か確認
- ローカルの場合はStreamlitアプリを再起動

**`Dify API Error 401`**
- Dify API キーが正しく設定されているか確認
- Difyアプリが公開状態になっているか確認

**`Dify API Error 400`**
- Chatflowの構成が正しいか確認
- System Promptが設定されているか確認

### パフォーマンス最適化
- 音声ファイルは5分以内を推奨
- 25MB超過時は自動圧縮されますが、元ファイルが小さい方が処理速度向上
- Difyのモデル選択で応答速度調整可能

## 📞 サポート

技術的な問題が発生した場合：
1. エラーメッセージの詳細を確認
2. ブラウザの開発者ツールでネットワークエラーをチェック
3. Streamlit Community Cloudの場合はログを確認
