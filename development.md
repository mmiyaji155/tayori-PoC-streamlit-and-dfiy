# 📝IC要約チャットシステム 開発手順書

## 🎯 概要

ユーザーが音声ファイルをアップロードすると、**OpenAI Whisper API** で文字起こしを行い、**Dify Chatflow** で要約を生成。さらに要約内容について継続的に質問できるチャットシステムです。

## 🏗️ システムアーキテクチャ

```
User ──→ Streamlit UI ──→ OpenAI Whisper API (文字起こし)
                    │
                    └──→ Dify Chatflow ──→ GPT-4o-mini (要約・質問応答)
                                    │
                                    └──→ 継続会話管理
```

## 🛠️ 技術スタック

| 層 | 技術 | バージョン | 用途 |
|---|---|---|---|
| フロントエンド | Streamlit | 1.36+ | UI・ファイル処理・チャット |
| 音声処理 | OpenAI Whisper API | whisper-1 | 音声→テキスト変換 |
| 音声圧縮 | pydub + FFmpeg | 0.25.1+ | 25MB制限対応 |
| 要約AI | Dify Cloud | latest | Chatflow管理・LLM実行 |
| LLM | GPT-4o-mini | latest | 要約生成・質問応答 |
| デプロイ | Streamlit Community Cloud | - | 本番環境 |

## 🔄 処理フロー詳細

### 1. ファイルアップロード・前処理
```python
# 1. ファイル受信（最大制限なし）
uf = st.file_uploader("音声ファイルをアップロード", type=[...])

# 2. サイズチェック・自動圧縮
if len(b) > 25*1024*1024:
    st.info("25 MB 超を検知 → 圧縮")
    b = compress_audio(b, uf.name)
```

### 2. 音声文字起こし
```python
# Whisper API呼び出し（最適化版）
def transcribe(chunks, key, fname):
    client = openai.OpenAI(api_key=key)
    texts = []
    for i, c in enumerate(chunks):
        f = io.BytesIO(c); f.name = f"chunk{i}.{fname.split('.')[-1]}"
        r = client.audio.transcriptions.create(
            model="whisper-1", file=f, language="ja"
        )
        texts.append(r.text)
    return " ".join(texts)
```

### 3. Dify要約生成（軽量化）
```python
# ストリーミング応答でリアルタイム生成
def ask_dify(query, dify_key, conv_id="", user_id="streamlit_user_1"):
    headers = {"Authorization": f"Bearer {dify_key}", "Content-Type": "application/json"}
    payload = {"query": query, "inputs": {}, "response_mode": "streaming",
               "conversation_id": conv_id, "user": user_id}

    with st.spinner("🌀 要約を生成中…"):
        r = requests.post("https://api.dify.ai/v1/chat-messages",
                          headers=headers, json=payload, timeout=120, stream=True)
```

### 4. 継続会話
- セッション状態で `conversation_id` を保持
- Difyの会話履歴機能で文脈を維持
- 追加質問・修正指示に対応

## 🚀 開発セットアップ

### 1. 環境構築
```bash
# プロジェクト初期化
mkdir voice_chat_system && cd voice_chat_system
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 依存関係インストール
pip install streamlit>=1.36.0 openai>=1.35.0 requests>=2.31.0 pydub>=0.25.1
```

### 2. 設定ファイル作成
```toml
# .streamlit/secrets.toml
OPENAI_API_KEY = "sk-..."
DIFY_API_KEY = "app-..."

# .streamlit/config.toml
[server]
maxUploadSize = 200  # MB
```

### 3. Dify Chatflow設定
1. **アプリ作成**: Chatflow タイプを選択
2. **ノード構成**:
   - Start ノード: `{{#start.text}}`
   - LLM ノード: GPT-4o-mini、System Prompt設定
   - End ノード: `{{#llm.text}}`
3. **API Key発行**: アプリ設定から生成

## 📝 主要機能実装（最新版）

### 軽量化された音声圧縮
```python
def compress_audio(b: bytes, fname: str, target_mb=24) -> bytes:
    ext = fname.split('.')[-1].lower() if '.' in fname else 'mp3'
    with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as t_in:
        t_in.write(b); in_path = t_in.name
    try:
        audio = AudioSegment.from_file(in_path)
        ratio = (target_mb*1024*1024*0.9) / len(b)
        br = "128k" if ratio>=.7 else "96k" if ratio>=.5 else "64k" if ratio>=.3 else "32k"
        if br in ("64k","32k"): 
            audio = audio.set_frame_rate(16000 if br=="32k" else 22050)
        # ... 処理続行
    finally:
        # クリーンアップ
```

### 統合されたUI設計
```python
# 最新のサイドバー設計
with st.sidebar:
    st.header("🔰 はじめに")
    
    # ユーザー視点の 3 ステップ手順
    st.markdown("""
### 🚀 かんたん 3 ステップ
1. **ファイルを選択 → アップロード**  
2. **自動処理を待つだけ**  
3. **チャットでやり取り**  
""")
    
    # できることリスト
    st.markdown("""
### 💡 このアプリで出来ること
- **ポイント要約**: 長い音声でも要点だけを読みやすく抽出  
- **フォロー質問**: 要約を材料に追加の質問や深掘りが可能  
- **要約の修正指示**: 「箇条書きを増やす」「専門用語を削る」などリライト要求  
""")
```

### ストリーミング応答の最適化
```python
# エラーハンドリング強化
for line in r.iter_lines(decode_unicode=True):
    if not line.startswith("data:"): continue
    obj = json.loads(line[5:].strip())
    if obj.get("event") == "message":
        chunks.append(obj.get("answer","")); new_id = obj.get("conversation_id", conv_id)
    elif obj.get("event") == "error":
        st.error(f"Dify error: {obj.get('message') or obj}"); return None, conv_id
    elif obj.get("event") == "message_end": break
```

## 🌐 デプロイメント

### Streamlit Community Cloud
1. **GitHubプッシュ**
```bash
git add .
git commit -m "Latest optimized version"
git push origin main
```

2. **アプリ作成**
- [Streamlit Community Cloud](https://share.streamlit.io)
- Repository・Branch・Main file指定

3. **Secrets設定**
```toml
OPENAI_API_KEY = "sk-..."
DIFY_API_KEY = "app-..."
```

## 🔧 最新の改善点

### コード軽量化
- 関数を統合してファイルサイズを大幅削減
- インポートの最適化
- 冗長なコメント・変数の整理

### UIエクスペリエンス向上
- サイドバーに分かりやすい手順説明を追加
- 絵文字とアイコンでビジュアル強化
- ユーザーの行動フローを明確化

### エラーハンドリング強化
```python
# 簡潔なエラー処理
try:
    st.error(f"Dify API {r.status_code}: {r.json()}")
except:
    st.error(f"Dify API {r.status_code}: {r.text[:200]}")
```

## 📊 運用・監視

### パフォーマンス指標
- **音声処理時間**: ファイルサイズ vs 処理時間
- **要約品質**: ユーザーフィードバック
- **API使用量**: OpenAI・Dify使用状況

### ログ・モニタリング
- Streamlit Community Cloud ログ
- Dify Dashboard 使用状況
- エラー率・応答時間監視

## 🎨 今後の拡張案

### 機能拡張
- 複数言語対応
- 音声ファイル形式拡張
- 要約スタイル選択機能
- エクスポート機能（PDF、Markdown）

### インテグレーション
- Google Drive連携
- Slack Bot化
- API化（REST API提供）
- データベース連携（会話履歴永続化）

## 🔍 トラブルシューティング

### 開発時のよくある問題
```python
# 1. ImportError: No module named 'pydub'
pip install pydub

# 2. FFmpeg not found
# Windows: choco install ffmpeg
# Mac: brew install ffmpeg

# 3. Secrets not found
# .streamlit/secrets.toml の存在・形式確認
```

### 本番環境でのデバッグ
- Streamlit Community Cloud ログ確認
- ブラウザ開発者ツール活用
- エラーメッセージの詳細化

---

この開発手順書に従うことで、軽量化されたスケーラブルで保守性の高い音声要約チャットシステムを構築できます。
