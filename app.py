import streamlit as st
import openai
import requests
import io
import os
from typing import Optional

# ページ設定
st.set_page_config(
    page_title="音声要約チャット",
    page_icon="🎤",
    layout="wide"
)

st.title("🎤 音声要約チャットシステム")
st.markdown("音声ファイルをアップロードして、AI が自動で文字起こし・要約を行います")

# API設定の確認
def check_api_keys():
    """API キーの設定確認"""
    try:
        openai_key = st.secrets["OPENAI_API_KEY"]
        dify_key = st.secrets["DIFY_API_KEY"]
        dify_app_id = st.secrets["DIFY_APP_ID"]
        return openai_key, dify_key, dify_app_id
    except KeyError as e:
        st.error(f"Streamlit Secrets に {e} が設定されていません")
        st.info("設定方法: Settings → Secrets から以下のキーを設定してください")
        st.code('''
OPENAI_API_KEY = "sk-..."
DIFY_API_KEY = "app-..."
DIFY_APP_ID = "xxxxxxxx"
        ''')
        return None, None, None

# チャット履歴の初期化
if "messages" not in st.session_state:
    st.session_state.messages = []

def split_audio_file(audio_bytes: bytes, max_chunk_size: int = 14 * 1024 * 1024) -> list:
    """音声ファイルをチャンクに分割"""
    chunks = []
    total_size = len(audio_bytes)
    
    if total_size <= max_chunk_size:
        return [audio_bytes]
    
    start = 0
    chunk_num = 0
    max_chunks = 10  # 最大10チャンク
    
    while start < total_size and chunk_num < max_chunks:
        end = min(start + max_chunk_size, total_size)
        chunks.append(audio_bytes[start:end])
        start = end
        chunk_num += 1
    
    return chunks

def transcribe_audio_chunks(chunks: list, openai_key: str) -> str:
    """Whisperを使用してチャンクを文字起こし"""
    client = openai.OpenAI(api_key=openai_key)
    transcripts = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, chunk in enumerate(chunks):
        status_text.text(f"文字起こし中... ({i+1}/{len(chunks)})")
        
        # チャンクをファイルオブジェクトとして準備
        audio_file = io.BytesIO(chunk)
        audio_file.name = f"audio_chunk_{i+1}.m4a"  # ファイル名を設定
        
        try:
            # Whisper APIで文字起こし
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ja"  # 日本語を指定
            )
            transcripts.append(response.text)
        except Exception as e:
            st.error(f"チャンク {i+1} の文字起こしでエラーが発生しました: {e}")
            return ""
        
        # プログレスバー更新
        progress_bar.progress((i + 1) / len(chunks))
    
    progress_bar.empty()
    status_text.empty()
    
    return " ".join(transcripts)

def send_to_dify(transcript: str, dify_key: str, dify_app_id: str, summary_prompt: str = "") -> Optional[str]:
    """Difyに文字起こし結果を送信して要約を取得"""
    
    # プロンプトの構築
    if summary_prompt:
        query = f"{summary_prompt}\n\n---\n{transcript}"
    else:
        query = transcript
    
    payload = {
        "query": query,
        "user": "streamlit_user_1"
    }
    
    headers = {
        "Authorization": f"Bearer {dify_key}",
        "X-Dify-App-Id": dify_app_id,
        "Content-Type": "application/json"
    }
    
    try:
        with st.spinner("要約を生成中..."):
            response = requests.post(
                "https://api.dify.ai/chat-messages",
                headers=headers,
                json=payload,
                timeout=120
            )
        
        if response.status_code == 200:
            result = response.json()
            return result.get("answer", "要約の生成に失敗しました")
        else:
            st.error(f"Dify API エラー: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        st.error(f"Dify との通信でエラーが発生しました: {e}")
        return None

# メイン処理
def main():
    # API キーの確認
    openai_key, dify_key, dify_app_id = check_api_keys()
    if not all([openai_key, dify_key, dify_app_id]):
        return
    
    # サイドバーでの設定
    with st.sidebar:
        st.header("設定")
        
        # 要約プロンプトの設定（オプション）
        summary_prompt = st.text_area(
            "要約プロンプト（オプション）",
            value="",
            help="空の場合、Dify Chatflow の System Prompt が使用されます",
            placeholder="以下の文字起こしを3つのポイントで要約してください。"
        )
        
        st.info("💡 **対応形式**: m4a, mp3, wav, flac, mp4, mpeg, mpga, oga, ogg, webm")
        st.info("📏 **ファイルサイズ**: 最大200MB")
    
    # チャット履歴の表示
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # ファイルアップロード
    uploaded_file = st.file_uploader(
        "音声ファイルをアップロードしてください",
        type=["m4a", "mp3", "wav", "flac", "mp4", "mpeg", "mpga", "oga", "ogg", "webm"],
        accept_multiple_files=False
    )
    
    if uploaded_file is not None:
        # ファイル情報表示
        file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
        st.info(f"📁 **ファイル**: {uploaded_file.name} ({file_size_mb:.1f} MB)")
        
        # ファイルサイズチェック
        if file_size_mb > 200:
            st.error("ファイルサイズが200MBを超えています。より小さいファイルをアップロードしてください。")
            return
        
        # 処理ボタン
        if st.button("🎤 文字起こし・要約を実行", type="primary"):
            
            # ユーザーメッセージを追加
            user_message = f"音声ファイル '{uploaded_file.name}' をアップロードしました"
            st.session_state.messages.append({"role": "user", "content": user_message})
            
            with st.chat_message("user"):
                st.markdown(user_message)
            
            with st.chat_message("assistant"):
                # 音声ファイルの読み込み
                audio_bytes = uploaded_file.getvalue()
                
                # チャンク分割
                st.info("🔄 音声ファイルを処理中...")
                chunks = split_audio_file(audio_bytes)
                
                if len(chunks) > 10:
                    st.error("ファイルが大きすぎます。10チャンク以下になるよう調整してください。")
                    return
                
                st.success(f"✅ {len(chunks)} 個のチャンクに分割しました")
                
                # 文字起こし実行
                st.info("🎯 Whisper による文字起こしを実行中...")
                transcript = transcribe_audio_chunks(chunks, openai_key)
                
                if not transcript:
                    st.error("文字起こしに失敗しました")
                    return
                
                st.success("✅ 文字起こし完了")
                
                # 文字起こし結果の表示（折りたたみ可能）
                with st.expander("📝 文字起こし結果を表示"):
                    st.text_area("文字起こし", value=transcript, height=200, disabled=True)
                
                # Dify で要約生成
                summary = send_to_dify(transcript, dify_key, dify_app_id, summary_prompt)
                
                if summary:
                    st.markdown("### 📊 要約結果")
                    st.markdown(summary)
                    
                    # アシスタントメッセージを追加
                    st.session_state.messages.append({"role": "assistant", "content": summary})
                else:
                    st.error("要約の生成に失敗しました")

if __name__ == "__main__":
    main()
