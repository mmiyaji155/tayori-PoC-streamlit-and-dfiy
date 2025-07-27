import streamlit as st
import openai
import requests
import io
import os
from typing import Optional
from pydub import AudioSegment
import tempfile

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

def split_audio_file(audio_bytes: bytes, max_chunk_size: int = 25 * 1024 * 1024) -> list:
    """音声ファイルをチェック（Whisper APIの25MB制限まで対応）"""
    total_size = len(audio_bytes)
    
    # 25MB以下の場合はそのまま処理
    if total_size <= max_chunk_size:
        return [audio_bytes]
    
    # 25MBを超える場合はエラー
    raise ValueError(f"ファイルサイズが{max_chunk_size / (1024*1024):.0f}MBを超えています（Whisper API制限）。より小さいファイルをアップロードしてください。")

def compress_audio(audio_bytes: bytes, original_filename: str, target_size_mb: int = 24) -> bytes:
    """
    音声ファイルを圧縮してターゲットサイズ以下に収める
    
    Args:
        audio_bytes: 元の音声データ
        original_filename: 元のファイル名（拡張子判定用）
        target_size_mb: ターゲットサイズ（MB）
        
    Returns:
        圧縮された音声データ（bytes）
    """
    try:
        # ファイル拡張子を取得
        file_extension = original_filename.split('.')[-1].lower() if '.' in original_filename else 'mp3'
        
        # 一時ファイルとして音声データを保存
        with tempfile.NamedTemporaryFile(suffix=f'.{file_extension}', delete=False) as temp_input:
            temp_input.write(audio_bytes)
            temp_input_path = temp_input.name
        
        try:
            # pydubで音声ファイルを読み込み
            audio = AudioSegment.from_file(temp_input_path)
            
            # 元のサイズとターゲットサイズを計算
            original_size_mb = len(audio_bytes) / (1024 * 1024)
            target_size_bytes = target_size_mb * 1024 * 1024
            
            # 圧縮率を計算（少し余裕をもたせる）
            compression_ratio = (target_size_bytes * 0.9) / len(audio_bytes)
            
            # 圧縮設定を決定
            if compression_ratio < 0.3:
                # 大幅圧縮が必要な場合
                new_bitrate = "32k"
                audio = audio.set_frame_rate(16000)  # サンプリングレート下げる
            elif compression_ratio < 0.5:
                # 中程度圧縮
                new_bitrate = "64k"
                audio = audio.set_frame_rate(22050)
            elif compression_ratio < 0.7:
                # 軽度圧縮
                new_bitrate = "96k"
            else:
                # 最小圧縮
                new_bitrate = "128k"
            
            # 一時出力ファイル
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_output:
                temp_output_path = temp_output.name
            
            # MP3形式で圧縮エクスポート
            audio.export(
                temp_output_path,
                format="mp3",
                bitrate=new_bitrate,
                parameters=["-q:a", "9"]  # 品質設定（0-9, 9が最小サイズ）
            )
            
            # 圧縮された音声データを読み込み
            with open(temp_output_path, 'rb') as f:
                compressed_bytes = f.read()
            
            # 一時ファイルを削除
            os.unlink(temp_output_path)
            
            compressed_size_mb = len(compressed_bytes) / (1024 * 1024)
            
            # 圧縮結果をログ出力
            st.info(f"🗜️ **音声圧縮完了**: {original_size_mb:.1f}MB → {compressed_size_mb:.1f}MB (ビットレート: {new_bitrate})")
            
            return compressed_bytes
            
        finally:
            # 入力一時ファイルを削除
            if os.path.exists(temp_input_path):
                os.unlink(temp_input_path)
                
    except Exception as e:
        st.error(f"音声圧縮でエラーが発生しました: {e}")
        # 圧縮に失敗した場合は元のデータを返す
        return audio_bytes

def transcribe_audio_chunks(chunks: list, openai_key: str, original_filename: str = "audio.m4a") -> str:
    """Whisperを使用してチャンクを文字起こし"""
    client = openai.OpenAI(api_key=openai_key)
    transcripts = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, chunk in enumerate(chunks):
        status_text.text(f"文字起こし中... ({i+1}/{len(chunks)})")
        
        # チャンクをファイルオブジェクトとして準備
        audio_file = io.BytesIO(chunk)
        # 元のファイル拡張子を保持
        file_extension = original_filename.split('.')[-1] if '.' in original_filename else 'm4a'
        audio_file.name = f"audio_chunk_{i+1}.{file_extension}"
        
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
        st.info("📏 **ファイルサイズ**: 制限なし（25MB超過時は自動圧縮）")
        st.success("🗜️ **自動圧縮**: 大きなファイルも自動で最適化して処理")
    
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
        
        # ファイルサイズに応じた処理方法を表示
        if file_size_mb > 25:
            st.warning(f"⚠️ ファイルサイズが25MBを超えています。実行時に自動で圧縮します。")
        elif file_size_mb > 20:
            st.info("ℹ️ ファイルサイズが大きいため、必要に応じて圧縮処理を行います。")
        
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
                original_size_mb = len(audio_bytes) / (1024 * 1024)
                
                # ファイルサイズチェックと圧縮処理
                st.info("🔄 音声ファイルを処理中...")
                
                # 25MBを超える場合は圧縮
                if original_size_mb > 25:
                    st.warning(f"ファイルサイズが25MBを超えているため圧縮します...")
                    audio_bytes = compress_audio(audio_bytes, uploaded_file.name)
                    final_size_mb = len(audio_bytes) / (1024 * 1024)
                    
                    # 圧縮後もサイズチェック
                    if final_size_mb > 25:
                        st.error("圧縮後もファイルサイズが25MBを超えています。より短い音声ファイルをアップロードしてください。")
                        return
                else:
                    final_size_mb = original_size_mb
                
                # 処理完了
                try:
                    chunks = [audio_bytes]  # 圧縮されたファイルは必ず25MB以下
                    st.success(f"✅ 音声ファイルを処理しました（最終サイズ: {final_size_mb:.1f}MB）")
                except Exception as e:
                    st.error(f"音声ファイルの処理でエラーが発生しました: {e}")
                    return
                
                # 文字起こし実行
                st.info("🎯 Whisper による文字起こしを実行中...")
                transcript = transcribe_audio_chunks(chunks, openai_key, uploaded_file.name)
                
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
