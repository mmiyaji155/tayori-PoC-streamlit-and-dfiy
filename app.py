import streamlit as st
import openai, json, requests, io, os, tempfile
from typing import Optional, Tuple
from pydub import AudioSegment
import numpy as np
import wave
from datetime import datetime
from uuid import uuid4

# 画面設定
st.set_page_config(page_title="音声・動画要約チャット", page_icon="🎥", layout="wide")
st.title("📝IC要約チャットシステム")
st.markdown("PCのマイクやアップロード音声・動画から **文字起こし → 要約** を行い、編集可能なUIで確認できます")

# セッションステート
if "recording" not in st.session_state:
    st.session_state.recording = False
if "recorded_audio" not in st.session_state:
    st.session_state.recorded_audio = None
if "transcript_text" not in st.session_state:
    st.session_state.transcript_text = ""
if "summary_text" not in st.session_state:
    st.session_state.summary_text = ""
if "editing_enabled" not in st.session_state:
    st.session_state.editing_enabled = False
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "audio_input_key" not in st.session_state:
    st.session_state.audio_input_key = 0


def save_audio_to_wav(audio_data, fs=44100):
    filename = "recorded_audio.wav"
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(audio_data.tobytes())
    return filename


def check_api_keys():
    try:
        return st.secrets["OPENAI_API_KEY"], st.secrets["DIFY_API_KEY"]
    except KeyError as e:
        st.error(f"Secrets に {e} がありません")
        return None, None


def is_video_file(filename):
    """動画ファイルかどうかを判定"""
    video_extensions = ['mp4', 'mov', 'avi', 'mkv', 'wmv', 'flv', 'webm', 'm4v']
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    return ext in video_extensions


def extract_audio_from_video(video_bytes, video_filename):
    """動画ファイルから音声を抽出"""
    try:
        st.info("🎬 動画から音声を抽出中...")
        
        # 動画の拡張子を取得
        ext = video_filename.split('.')[-1].lower() if '.' in video_filename else 'mp4'
        
        # 一時ファイルに動画を保存
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as temp_video:
            temp_video.write(video_bytes)
            video_path = temp_video.name
        
        try:
            # 動画から音声を抽出
            audio = AudioSegment.from_file(video_path)
            
            # 音声を一時ファイルに保存
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
                audio_path = temp_audio.name
            
            # WAV形式で保存（Whisperに適した形式）
            audio.export(audio_path, format="wav")
            
            # 音声ファイルを読み込み
            with open(audio_path, 'rb') as audio_file:
                audio_bytes = audio_file.read()
            
            # 一時ファイルを削除
            os.unlink(audio_path)
            
            st.success("✅ 音声抽出完了")
            return audio_bytes
            
        finally:
            # 動画ファイルを削除
            if os.path.exists(video_path):
                os.unlink(video_path)
                
    except Exception as e:
        st.error(f"❌ 動画から音声の抽出に失敗しました: {e}")
        st.warning("💡 対応形式: MP4, MOV, AVI, MKV, WMV, FLV, WebM, M4V")
        return None


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
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as t_out:
            out_path = t_out.name
        audio.export(out_path, format="mp3", bitrate=br, parameters=["-q:a","9"])
        return open(out_path,'rb').read()
    finally:
        for p in (in_path, locals().get('out_path')):
            if p and os.path.exists(p):
                os.unlink(p)


def transcribe(chunks, key, fname):
    st.info("📝 文字起こしを開始…")
    client = openai.OpenAI(api_key=key)
    texts = []
    for i, c in enumerate(chunks):
        f = io.BytesIO(c); f.name = f"chunk{i}.{fname.split('.')[-1]}"
        r = client.audio.transcriptions.create(model="whisper-1", file=f, language="ja")
        texts.append(r.text)
    st.success("✅ 文字起こし完了")
    return " ".join(texts)


def ask_dify(query: str,
             dify_key: str,
             conv_id: str = "",
             user_id: Optional[str] = None
            ) -> Tuple[Optional[str|dict], Optional[str]]:
    """
    Dify へストリーミング送信し、要約を受け取る
    戻り値: (answer文字列, conversation_id)
    """
    url = "https://api.dify.ai/v1/chat-messages"

    # user_id が指定されなければ uuid を生成
    if not user_id:
        if "dify_user_id" not in st.session_state:
            st.session_state.dify_user_id = f"streamlit-{uuid4()}"
        user_id = st.session_state.dify_user_id

    headers = {
        "Authorization": f"Bearer {dify_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    payload = {
        "query": query,
        "inputs": {},
        "response_mode": "streaming",
        "user": user_id,   # ★必須
    }
    if conv_id:  # 空文字は送らない
        payload["conversation_id"] = conv_id

    st.info("📝 要約を開始します…")
    with st.spinner("要約を作成しています…"):
        try:
            r = requests.post(url, headers=headers, json=payload,
                              timeout=120, stream=True)
        except requests.RequestException as e:
            st.error(f"Dify API リクエスト失敗: {e}")
            return None, None

        if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("text/event-stream"):
            chunks, new_conv_id = [], conv_id
            try:
                for raw in r.iter_lines(decode_unicode=True):
                    if not raw or not raw.startswith("data:"):
                        continue
                    data = raw[5:].strip()
                    if data in ("[DONE]", ""):
                        continue
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    ev = obj.get("event")
                    if ev == "message":
                        chunks.append(obj.get("answer", ""))
                        new_conv_id = obj.get("conversation_id", new_conv_id)
                    elif ev == "message_replace":
                        repl = obj.get("answer", "")
                        chunks = [repl] if repl else chunks
                    elif ev == "message_end":
                        new_conv_id = obj.get("conversation_id", new_conv_id)
                        break
                    elif ev == "error":
                        st.error(f"Dify error: {obj.get('message') or obj}")
                        return None, conv_id
                    else:
                        continue
                return "".join(chunks), new_conv_id
            
            except (requests.exceptions.ChunkedEncodingError, 
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                st.error(f"ストリーミング中にネットワークエラーが発生しました: {e}")
                st.warning("⚠️ 通信が途切れました。もう一度お試しください。")
                return None, conv_id
            except Exception as e:
                st.error(f"予期しないエラーが発生しました: {e}")
                return None, conv_id

        if r.status_code == 200:
            try:
                js = r.json()
            except Exception:
                st.error(f"Dify API 形式エラー: {r.text[:200]}")
                return None, None
            return js.get("answer", ""), js.get("conversation_id", "")

        try:
            st.error(f"Dify API {r.status_code}: {r.json()}")
        except Exception:
            st.error(f"Dify API {r.status_code}: {r.text[:200]}")
        return None, None


def set_flag(name: str, value: bool = True):
    st.session_state[name] = value


def calculate_textarea_height(text, min_height=100, line_height=20, max_height=3500):
    """テキストの行数に基づいて適切な高さを計算"""
    if not text:
        return min_height
    
    lines = text.count('\n') + 1
    calculated_height = max(min_height, lines * line_height + 40)  # +40はpadding等
    return min(calculated_height, max_height)


def clear_audio_input():
    """録音データをクリア"""
    st.session_state.audio_input_key += 1


def clear_uploaded_file():
    """アップロードファイルをクリア"""
    st.session_state.uploader_key += 1


def clear_all_audio():
    """全ての音声データをクリア"""
    st.session_state.uploader_key += 1
    st.session_state.audio_input_key += 1


def get_file_type_info(filename):
    """ファイルタイプの情報を取得"""
    if is_video_file(filename):
        return "🎬", "動画", "video"
    else:
        return "🎵", "音声", "audio"


def main():
    st.markdown("""
<style>
/* --- TextArea (disabled) のグレーを解除 --- */
div[data-testid="stTextArea"] [data-baseweb="textarea"] {
  opacity: 1 !important;
}

div[data-testid="stTextArea"] textarea:disabled,
div[data-testid="stTextArea"] textarea[disabled]{
  background-color: transparent !important;
  color: inherit !important;
  -webkit-text-fill-color: inherit !important;
  opacity: 1 !important;
  box-shadow: none !important;
  border-color: rgba(49, 51, 63, 0.2) !important;
}

div[data-testid="stTextArea"] label,
div[data-testid="stTextArea"] > div {
  opacity: 1 !important;
}

/* --- モダンなカードスタイル（グラデーション削除） --- */
.audio-card {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 12px;
    padding: 24px;
    margin: 16px 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.upload-card {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 12px;
    padding: 24px;
    margin: 16px 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.video-card {
    background: linear-gradient(135deg, #fff5f5 0%, #f8f9fa 100%);
    border: 1px solid #fecaca;
    border-radius: 12px;
    padding: 24px;
    margin: 16px 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* --- 統一されたボタンスタイル --- */
.stButton > button {
    background: #007bff !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 12px 24px !important;
    font-size: 14px !important;
    transition: background-color 0.2s ease !important;
    width: 100% !important;
}

.stButton > button:hover {
    background: #0056b3 !important;
}

/* セカンダリボタン */
.stButton > button[kind="secondary"] {
    background: #6c757d !important;
}

.stButton > button[kind="secondary"]:hover {
    background: #545b62 !important;
}

/* プライマリボタン（目立たせる） */
.stButton > button[kind="primary"] {
    background: #28a745 !important;
    font-size: 16px !important;
    padding: 16px 32px !important;
    font-weight: 700 !important;
}

.stButton > button[kind="primary"]:hover {
    background: #1e7e34 !important;
}

/* クリアボタン（危険操作用） */
.clear-button > button {
    background: #dc3545 !important;
    color: white !important;
}

.clear-button > button:hover {
    background: #c82333 !important;
}

/* ステータスバッジ（アニメーション削除） */
.status-badge {
    display: inline-block;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 0.85em;
    font-weight: 600;
    margin: 8px 0;
}

.status-success {
    background: #d4edda;
    color: #155724;
    border: 1px solid #c3e6cb;
}

.status-info {
    background: #d1ecf1;
    color: #0c5460;
    border: 1px solid #bee5eb;
}

.status-video {
    background: #f8d7da;
    color: #721c24;
    border: 1px solid #f5c6cb;
}

/* セクションヘッダー */
.section-header {
    font-size: 1.2em;
    font-weight: 700;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: #495057;
}

.icon {
    font-size: 1.4em;
}

/* タブの背景色（アクティブ状態を分かりやすく） */
div[data-baseweb="tab-list"] {
    background: #f8f9fa;
    border-radius: 8px;
    padding: 4px;
    margin-bottom: 20px;
}

div[data-baseweb="tab"] {
    border-radius: 6px !important;
    font-weight: 600 !important;
}

div[data-baseweb="tab"][aria-selected="true"] {
    background: white !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
}

/* プロセスボックス */
.process-box {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 12px;
    padding: 24px;
    margin: 16px 0;
}

.process-ready {
    background: #e8f5e8;
    border-color: #28a745;
}

.process-upload {
    background: #e3f2fd;
    border-color: #2196f3;
}

.process-video {
    background: #fff3cd;
    border-color: #856404;
}

/* ファイルアップローダーのスタイル調整 */
div[data-testid="stFileUploader"] {
    background: white;
    border-radius: 8px;
    padding: 16px;
    border: 2px dashed #dee2e6;
    margin: 16px 0;
}

div[data-testid="stFileUploader"]:hover {
    border-color: #007bff;
}

/* 全体の配置を揃える */
.stContainer > div {
    padding-left: 0 !important;
    padding-right: 0 !important;
}

/* 端揃えの修正 */
div[data-testid="stVerticalBlock"] > div[style*="width"] {
    width: 100% !important;
    max-width: 100% !important;
}

/* --- audio_input のスタイル調整 --- */
div[data-testid="stAudioInput"] {
    background: white;
    border-radius: 8px;
    padding: 16px;
    margin: 16px 0;
}

/* モバイル用の追加スタイル */
@media (max-width: 768px) {
    .audio-card, .upload-card, .video-card {
        padding: 16px;
        margin: 8px 0;
    }
    
    .stButton > button {
        padding: 16px 20px !important;
        font-size: 16px !important;
        min-height: 48px !important;
    }
    
    div[data-testid="stAudioInput"] {
        padding: 20px 16px;
    }
}

/* iPhone Safari 用の追加調整 */
@supports (-webkit-touch-callout: none) {
    .stButton > button {
        -webkit-appearance: button;
        min-height: 44px !important;
    }
}
</style>
""", unsafe_allow_html=True)

    
    openai_key, dify_key = check_api_keys()
    if not all([openai_key, dify_key]):
        return

    # ---- セッション初期化 ----
    st.session_state.setdefault("recorded_audio_data", None)
    st.session_state.setdefault("transcript_text", "")
    st.session_state.setdefault("summary_text", "")
    st.session_state.setdefault("editing_enabled", False)

    st.header("🎵 音声・動画入力")

    # タブでの選択
    tab1, tab2 = st.tabs(["🎙️ 録音", "📁 ファイルアップロード"])
    
    # ==============================
    # 録音タブ - st.audio_input() を使用
    # ==============================
    with tab1:
        st.markdown("""
        <div class="audio-card">
            <div class="section-header">
                <span class="icon">🎤</span>
                <span>マイクから録音</span>
            </div>
            <p style="margin-bottom: 20px; color: #6c757d;">
                下のボタンで録音できます。📱スマホでも利用可能です。
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # 録音コントロール
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Streamlit標準のaudio_inputを使用（モバイル対応）
            audio_bytes = st.audio_input(
                "録音ボタンを押して音声を録音",
                key=f"audio_input_{st.session_state.audio_input_key}"
            )
            
            if audio_bytes:
                st.session_state.recorded_audio_data = audio_bytes
                
        with col2:
            # 録音データがある場合のみクリアボタンを表示
            if st.session_state.get("recorded_audio_data") is not None:
                with st.container():
                    st.markdown('<div class="clear-button">', unsafe_allow_html=True)
                    if st.button("🗑️ クリア", key="clear_recorded_btn", use_container_width=True):
                        clear_audio_input()
                        st.session_state.recorded_audio_data = None
                        st.toast("🗑️ 録音データをクリアしました", icon="✅")
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

        # 録音データの状態表示
        if st.session_state.get("recorded_audio_data") is not None:
            st.markdown("""
            <div class="status-badge status-success">
                ✅ 録音データ準備完了
            </div>
            """, unsafe_allow_html=True)
            st.audio(st.session_state.recorded_audio_data, format="audio/wav")

    # ==============================
    # ファイルアップロードタブ
    # ==============================
    with tab2:
        st.markdown("""
        <div class="upload-card">
            <div class="section-header">
                <span class="icon">📁</span>
                <span>音声・動画ファイルをアップロード</span>
            </div>
            <p style="margin-bottom: 20px; color: #6c757d;">
                <strong>🎵 音声:</strong> MP3, WAV, M4A, FLAC<br>
                <strong>🎬 動画:</strong> MP4, MOV, AVI, MKV, WMV, FLV, WebM, M4V
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # アップロード部分
        col1, col2 = st.columns([3, 1])
        
        with col1:
            uf = st.file_uploader(
                "ファイルを選択またはドラッグ&ドロップ", 
                type=["m4a", "mp3", "wav", "flac", "mp4", "mov", "avi", "mkv", "wmv", "flv", "webm", "m4v"],
                key=f"file_uploader_{st.session_state.uploader_key}",
                label_visibility="collapsed"
            )
        
        with col2:
            # アップロードファイルがある場合のみクリアボタンを表示
            if uf is not None:
                with st.container():
                    st.markdown('<div class="clear-button">', unsafe_allow_html=True)
                    if st.button("🗑️ クリア", key="clear_uploaded_btn", use_container_width=True):
                        clear_uploaded_file()
                        st.toast("🗑️ アップロードファイルをクリアしました", icon="✅")
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

        # アップロードファイルの状態表示
        if uf is not None:
            icon, file_type, _ = get_file_type_info(uf.name)
            badge_class = "status-video" if is_video_file(uf.name) else "status-info"
            
            st.markdown(f"""
            <div class="status-badge {badge_class}">
                {icon} {uf.name} ({file_type}ファイル) アップロード完了
            </div>
            """, unsafe_allow_html=True)
            
            # 動画ファイルの場合は動画プレーヤー、音声ファイルの場合は音声プレーヤー
            if is_video_file(uf.name):
                st.video(uf.getvalue())
            else:
                st.audio(uf.getvalue())

    # ==============================
    # 音声処理セクション
    # ==============================
    b = None
    fname = None
    is_video = False

    # 使用する音声の判定と表示
    if st.session_state.get("recorded_audio_data") is not None:
        b = st.session_state.recorded_audio_data
        fname = "mic_recorded.wav"
        is_video = False
        
    elif uf:
        b = uf.getvalue()
        fname = uf.name
        is_video = is_video_file(fname)

    # 処理ボタンの表示
    if b and fname:
        # ✅ 最初にbytesに変換（UploadedFile対応）
        if hasattr(b, 'getvalue'):
            file_bytes = b.getvalue()  # UploadedFile → bytes
        else:
            file_bytes = b  # 既にbytesの場合
        
        st.markdown("---")
        st.markdown("### 🚀 音声・動画処理")
        
        # ファイル情報の表示
        col1, col2 = st.columns([2, 1])
        
        with col1:
            if st.session_state.get("recorded_audio_data") is not None:
                st.markdown("""
                <div class="process-box process-ready">
                    <h4 style="margin: 0; color: #155724;">🎙️ 録音データを処理します</h4>
                    <p style="margin: 8px 0 0 0; color: #155724; opacity: 0.8;">マイクから録音された音声</p>
                </div>
                """, unsafe_allow_html=True)
            elif is_video:
                icon, file_type, _ = get_file_type_info(fname)
                st.markdown(f"""
                <div class="process-box process-video">
                    <h4 style="margin: 0; color: #856404;">{icon} {fname} を処理します</h4>
                    <p style="margin: 8px 0 0 0; color: #856404; opacity: 0.8;">動画ファイル → 音声抽出 → 文字起こし</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                icon, file_type, _ = get_file_type_info(fname)
                st.markdown(f"""
                <div class="process-box process-upload">
                    <h4 style="margin: 0; color: #0c5460;">{icon} {fname} を処理します</h4>
                    <p style="margin: 8px 0 0 0; color: #0c5460; opacity: 0.8;">音声ファイル → 文字起こし</p>
                </div>
                """, unsafe_allow_html=True)
        
        with col2:
            # ✅ 変換済みbytesを使用
            size_mb = len(file_bytes) / (1024 * 1024)
            st.metric("ファイルサイズ", f"{size_mb:.1f} MB")
            
            if size_mb > 25:
                st.warning("⚠️ 25MB超のため圧縮されます")

        # 処理ボタン
        st.markdown("<br>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            button_text = "🎬 動画処理 → 文字起こし → 要約を開始" if is_video else "🔊 文字起こし → 要約を開始"
            process_button = st.button(
                button_text,
                key="process_audio_btn",
                type="primary",
                use_container_width=True
            )
        
        if process_button:
            audio_bytes = file_bytes
            
            # 動画ファイルの場合は音声を抽出
            if is_video:
                audio_bytes = extract_audio_from_video(file_bytes, fname)
                if audio_bytes is None:
                    st.stop()  # エラーで処理を停止
                fname = fname.rsplit('.', 1)[0] + '.wav'  # 拡張子をwavに変更

            # 音声圧縮（必要に応じて）
            if len(audio_bytes) > 25 * 1024 * 1024:
                st.info("25MB超を検知 → 音声を圧縮")
                audio_bytes = compress_audio(audio_bytes, fname)

            # 文字起こし
            transcript = transcribe([audio_bytes], openai_key, fname)

            prompt = f"{transcript}"

            # ▼ ask_dify は (answer_str_or_dict, conversation_id) を返す
            answer, new_conv_id = ask_dify(
                prompt,
                dify_key,
                conv_id=st.session_state.get("dify_conversation_id", ""),
                user_id=st.session_state.get("dify_user_id")
            )

            # 会話IDを更新（継続利用する場合に備える）
            if new_conv_id:
                st.session_state.dify_conversation_id = new_conv_id

            # 受け取りチェック
            if not answer:
                st.error("Difyから要約が受け取れませんでした。")
            else:
                # answer は文字列の JSON（ブロッキングフォールバック時は dict の可能性）
                try:
                    if isinstance(answer, str):
                        result = json.loads(answer)
                    else:
                        result = answer  # すでに dict の場合
                except json.JSONDecodeError as e:
                    st.error(f"要約のJSONパースに失敗しました: {e}")
                    st.caption("受信内容（先頭200文字）:")
                    st.code(str(answer)[:200])
                    result = {}

                st.session_state.transcript_text = result.get("transcript", "")
                st.session_state.summary_text   = result.get("summary", "")
                st.session_state.editing_enabled = False

    # ==============================
    # 出力表示・編集・保存
    # ==============================
    # 個別の編集フラグを初期化
    st.session_state.setdefault("editing_transcript", False)
    st.session_state.setdefault("editing_summary", False)

    if st.session_state.transcript_text or st.session_state.summary_text:
        st.subheader("📝 出力内容")

        # ===== Summary =====
        with st.container(border=True):
            st.markdown("**📖 要約**")

            if st.session_state.editing_summary:
                height = calculate_textarea_height(st.session_state.summary_text, min_height=100, line_height=20, max_height=3500)
                new_s = st.text_area(
                    "（編集中）要約",
                    value=st.session_state.summary_text,
                    height=height,
                    key="summary_edit",
                )
                c1, c2 = st.columns([0.5, 0.5])
                
                # 保存ボタン
                if c1.button(
                    "💾 保存",
                    key="save_summary_btn",
                    use_container_width=True,
                ):
                    st.session_state.summary_text = st.session_state.summary_edit
                    st.session_state.editing_summary = False
                    st.rerun()
                
                # キャンセルボタン
                if c2.button(
                    "↩️ キャンセル",
                    key="cancel_summary_btn",
                    use_container_width=True,
                ):
                    st.session_state.editing_summary = False
                    st.rerun()
            else:
                height = calculate_textarea_height(st.session_state.summary_text, min_height=100, line_height=20, max_height=3500)
                st.text_area(
                    "要約（閲覧モード）",
                    value=st.session_state.summary_text,
                    height=height,
                    key="summary_view",
                    disabled=True,
                )
                c1, c2 = st.columns([0.5, 0.5])
                c1.button(
                    "✏️ 編集する",
                    key="edit_summary_btn",
                    use_container_width=True,
                    on_click=set_flag,
                    args=("editing_summary", True),
                )
                c2.download_button(
                    "💾 テキスト保存",
                    data=st.session_state.summary_text,
                    file_name="summary.txt",
                    mime="text/plain",
                    key="dl_btn_summary",
                    use_container_width=True,
                )

        # ===== Transcript =====
        with st.container(border=True):
            st.markdown("**📰 文字起こし**")

            if st.session_state.editing_transcript:
                height = calculate_textarea_height(st.session_state.transcript_text)
                new_t = st.text_area(
                    "（編集中）文字起こし",
                    value=st.session_state.transcript_text,
                    height=height,
                    key="transcript_edit",
                )
                c1, c2 = st.columns([0.5, 0.5])
                
                # 保存ボタン
                if c1.button(
                    "💾 保存",
                    key="save_transcript_btn",
                    use_container_width=True,
                ):
                    st.session_state.transcript_text = st.session_state.transcript_edit
                    st.session_state.editing_transcript = False
                    st.rerun()
                
                # キャンセルボタン
                if c2.button(
                    "↩️ キャンセル",
                    key="cancel_transcript_btn",
                    use_container_width=True,
                ):
                    st.session_state.editing_transcript = False
                    st.rerun()
            else:
                height = calculate_textarea_height(st.session_state.transcript_text)
                st.text_area(
                    "文字起こし（閲覧モード）",
                    value=st.session_state.transcript_text,
                    height=height,
                    key="transcript_view",
                    disabled=True,
                )
                c1, c2 = st.columns([0.5, 0.5])
                c1.button(
                    "✏️ 編集する",
                    key="edit_transcript_btn",
                    use_container_width=True,
                    on_click=set_flag,
                    args=("editing_transcript", True),
                )
                c2.download_button(
                    "💾 テキスト保存",
                    data=st.session_state.transcript_text,
                    file_name="transcript.txt",
                    mime="text/plain",
                    key="dl_btn_transcript",
                    use_container_width=True,
                )


if __name__ == "__main__":
    main()