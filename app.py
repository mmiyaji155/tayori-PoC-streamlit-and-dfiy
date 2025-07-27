import streamlit as st
import openai, json, requests, io, os, tempfile
from typing import Optional
from pydub import AudioSegment

# ─────────────────── 1. 画面設定 ───────────────────
st.set_page_config(page_title="音声要約チャット", page_icon="🎤", layout="wide")
st.title("📝IC要約チャットシステム")
st.markdown("音声ファイルをアップロードして、AI が **文字起こし → 要約** を行い、その内容について質問できます。")

with st.expander("📖 使い方", expanded=False):
    st.markdown("""
1. **音声ファイルをアップロード**  
2. **文字起こし**→ **要約生成**  
3. 要約内容についてチャットで質問
""")

# ─────────────────── 2. ユーティリティ ───────────────────
def check_api_keys():
    try:
        return st.secrets["OPENAI_API_KEY"], st.secrets["DIFY_API_KEY"]
    except KeyError as e:
        st.error(f"Secrets に {e} がありません"); return None, None

def compress_audio(b: bytes, fname: str, target_mb=24) -> bytes:
    ext = fname.split('.')[-1].lower() if '.' in fname else 'mp3'
    with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as t_in:
        t_in.write(b); in_path = t_in.name
    try:
        audio = AudioSegment.from_file(in_path)
        ratio = (target_mb*1024*1024*0.9) / len(b)
        br = "128k" if ratio>=.7 else "96k" if ratio>=.5 else "64k" if ratio>=.3 else "32k"
        if br in ("64k","32k"): audio = audio.set_frame_rate(16000 if br=="32k" else 22050)
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as t_out:
            out_path = t_out.name
        audio.export(out_path, format="mp3", bitrate=br, parameters=["-q:a","9"])
        return open(out_path,'rb').read()
    finally:
        for p in (in_path, locals().get('out_path')):
            if p and os.path.exists(p): os.unlink(p)

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

def ask_dify(query: str, dify_key: str,
             conv_id: str = "", user_id: str = "streamlit_user_1") -> tuple[Optional[str], Optional[str]]:

    headers = {"Authorization": f"Bearer {dify_key}", "Content-Type": "application/json"}
    payload = {"query": query, "inputs": {}, "response_mode": "streaming",
               "conversation_id": conv_id, "user": user_id}

    with st.spinner("🌀 要約を生成中…"):
        r = requests.post("https://api.dify.ai/v1/chat-messages",
                          headers=headers, json=payload, timeout=120, stream=True)

    if r.status_code == 200 and r.headers.get("Content-Type","").startswith("text/event-stream"):
        chunks, new_id = [], conv_id
        for line in r.iter_lines(decode_unicode=True):
            if not line.startswith("data:"): continue
            obj = json.loads(line[5:].strip())
            if obj.get("event") == "message":
                chunks.append(obj.get("answer","")); new_id = obj.get("conversation_id", conv_id)
            elif obj.get("event") == "error":
                st.error(f"Dify error: {obj.get('message') or obj}"); return None, conv_id
            elif obj.get("event") == "message_end": break
        return "".join(chunks), new_id

    if r.status_code == 200:
        js = r.json(); return js.get("answer",""), js.get("conversation_id","")
    try:
        st.error(f"Dify API {r.status_code}: {r.json()}")
    except:
        st.error(f"Dify API {r.status_code}: {r.text[:200]}")
    return None, None

# ─────────────────── 3. セッション初期化 ───────────────────
if "messages" not in st.session_state: st.session_state.messages = []
if "conversation_id" not in st.session_state: st.session_state.conversation_id = ""

# ─────────────────── 4. メイン UI ───────────────────
def main():
    openai_key, dify_key = check_api_keys()
    if not all([openai_key, dify_key]): return

    # ─ sidebar ─────────────────────────────────────────
    with st.sidebar:
        st.header("🔰 はじめに")

        # ★ NEW: ユーザー視点の 3 ステップ手順
        st.markdown(
            """
### 🚀 かんたん 3 ステップ
1. **ファイルを選択 → アップロード**  
   - m4a / mp3 / wav / flac / mp4 … 主要フォーマット対応  
   - 25 MB 超なら自動でサイズ調整します
2. **自動処理を待つだけ**  
   - Whisper が文字起こし → Dify が要約を生成  
   - 生成が終わると要約がチャットに表示されます
3. **チャットでやり取り**  
   - 要約を読んで「もっと詳しく」「◯◯を削除して」など自由に質問・修正指示  
   - 追加質問にも要約内容を踏まえて回答します
""",
            unsafe_allow_html=True
        )

        # ★ NEW: できることリスト
        st.markdown(
            """
### 💡 このアプリで出来ること
- **ポイント要約**: 長い音声でも要点だけを読みやすく抽出  
- **フォロー質問**: 要約を材料に追加の質問や深掘りが可能  
- **要約の修正指示**: 「箇条書きを増やす」「専門用語を削る」などリライト要求  
- **履歴維持**: 同じ画面で会話を続けると過去の要約を踏まえて回答
""",
            unsafe_allow_html=True
        )

        # 要約プロンプト入力（任意）
        prompt = st.text_area(
            "🖋️ 追加要約プロンプト（任意）",
            "",
            height=120,
            placeholder="特別に指示したいことがあれば入力してください",
        )

    # ─ chat history
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    # ─ file upload
    uf = st.file_uploader("音声ファイルをアップロード", type=[
        "m4a","mp3","wav","flac","mp4","mpeg","mpga","oga","ogg","webm"])
    if uf and st.button("🎤 文字起こし → 要約"):
        user_msg = f"音声ファイル **{uf.name}** をアップロードしました"
        st.session_state.messages.append({"role":"user","content":user_msg})
        with st.chat_message("user"): st.markdown(user_msg)

        with st.chat_message("assistant"):
            b = uf.getvalue()
            if len(b) > 25*1024*1024:
                st.info("25 MB 超を検知 → 圧縮"); b = compress_audio(b, uf.name)
            transcript = transcribe([b], openai_key, uf.name)
            q = f"{prompt}\n\n---\n{transcript}" if prompt else transcript
            answer, cid = ask_dify(q, dify_key)
            if answer:
                st.markdown(answer)
                st.session_state.messages.append({"role":"assistant","content":answer})
                st.session_state.conversation_id = cid
            else:
                st.error("要約の生成に失敗しました")

    # ─ question mode
    if st.session_state.conversation_id:
        qtxt = st.chat_input("要約について質問してください…")
        if qtxt:
            st.session_state.messages.append({"role":"user","content":qtxt})
            with st.chat_message("user"): st.markdown(qtxt)
            with st.chat_message("assistant"):
                a, cid = ask_dify(qtxt, dify_key, st.session_state.conversation_id)
                if a:
                    st.markdown(a); st.session_state.messages.append({"role":"assistant","content":a})
                    st.session_state.conversation_id = cid
                else:
                    st.error("回答の生成に失敗しました")

if __name__ == "__main__":
    main()
