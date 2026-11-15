import os
import re
import json
import time
import zipfile
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="ClipForge AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ------------------------------ Design -------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { color-scheme: dark; }
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp {
  background:
    radial-gradient(ellipse at 8% 0%, rgba(115,89,255,.19), transparent 32%),
    radial-gradient(ellipse at 92% 10%, rgba(0,205,180,.10), transparent 27%),
    #0a0b11;
}
.block-container { max-width: 1180px; padding-top: 1.3rem; padding-bottom: 3rem; }
[data-testid="stHeader"] { background: rgba(0,0,0,0); }
.hero {
  border: 1px solid rgba(160,150,255,.23); border-radius: 25px;
  padding: 28px 30px; margin-bottom: 20px;
  background: linear-gradient(115deg,rgba(35,34,69,.97),rgba(20,24,39,.96) 60%,rgba(14,48,51,.88));
  box-shadow: 0 18px 60px rgba(0,0,0,.24);
}
.brand { font-family:'Space Grotesk',sans-serif; font-weight:700; letter-spacing:-1.7px; font-size:clamp(2rem,5vw,3.2rem); margin:0; }
.brand span { color:#a99aff; }
.tagline { color:#b8bfd2; margin-top:6px; font-size:1rem; }
.pill {
 display:inline-block; padding:5px 10px; border:1px solid rgba(179,167,255,.35);
 border-radius:999px; color:#c9c0ff; font-size:.75rem; font-weight:700;
 background:rgba(135,112,255,.10); margin-bottom:10px;
}
.section-title {font-family:'Space Grotesk',sans-serif; font-size:1.22rem; font-weight:700; margin:8px 0 12px;}
.panel {
 background:linear-gradient(145deg,rgba(24,27,42,.98),rgba(17,19,29,.98));
 border:1px solid #2a2e43; border-radius:19px; padding:18px;
}
.muted {color:#9ca5bd;font-size:.88rem;}
.stat {
 background:#171a29;border:1px solid #2b3047;border-radius:15px;padding:13px 15px;
}
.stat .num {font-family:'Space Grotesk';font-size:1.4rem;font-weight:700;}
.stat .lab {color:#9da6bc;font-size:.78rem;}
div.stButton > button, div.stDownloadButton > button {
 border-radius:12px; min-height:44px; font-weight:700; border:1px solid #45416d;
}
div.stButton > button[kind="primary"] {background:linear-gradient(100deg,#7662ff,#9a69f7);border:0;}
div[data-testid="stFileUploader"] section {background:#151827;border:1px dashed #55517b;border-radius:14px;}
div[data-testid="stTextInput"] input {border-radius:12px;}
hr {border-color:#282c3e;}
a {color:#b9aaff!important;}
@media(max-width:700px){.hero{padding:21px}.block-container{padding-left:1rem;padding-right:1rem}}
</style>
<div class="hero">
  <div class="pill">AI-POWERED VIDEO WORKSPACE</div>
  <h1 class="brand">CLIPFORGE <span>AI</span></h1>
  <div class="tagline">Turn long videos into short-form highlights — faster.</div>
</div>
""", unsafe_allow_html=True)

# ------------------------------ Helpers ------------------------------------
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or "Processing failed.")[-3000:])
    return p.stdout

def ffmpeg_ok():
    try:
        run(["ffmpeg", "-version"])
        run(["ffprobe", "-version"])
        return True
    except Exception:
        return False

def identify_link(raw):
    raw = (raw or "").strip()
    if not raw:
        return {"kind": "empty", "label": "No link entered"}
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    p = urlparse(raw)
    host = (p.hostname or "").lower()
    if not host:
        return {"kind": "invalid", "label": "This doesn't look like a valid web link", "url": raw}
    if host in ("youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com") or host.endswith(".youtube.com"):
        vid = None
        if host == "youtu.be":
            vid = p.path.strip("/").split("/")[0]
        else:
            q = parse_qs(p.query)
            vid = (q.get("v") or [None])[0]
            if not vid:
                m = re.search(r"/(?:shorts|embed|live)/([^/?]+)", p.path)
                vid = m.group(1) if m else None
        return {"kind": "youtube", "label": "YouTube video", "url": raw, "video_id": vid}
    if host == "twitch.tv" or host.endswith(".twitch.tv"):
        return {"kind": "twitch", "label": "Twitch stream or VOD", "url": raw}
    if host.endswith("tiktok.com"):
        return {"kind": "tiktok", "label": "TikTok video", "url": raw}
    if host.endswith("instagram.com"):
        return {"kind": "instagram", "label": "Instagram post or Reel", "url": raw}
    if host.endswith("vimeo.com"):
        return {"kind": "vimeo", "label": "Vimeo video", "url": raw}
    if host.endswith("facebook.com") or host == "fb.watch":
        return {"kind": "facebook", "label": "Facebook video", "url": raw}
    if host.endswith("x.com") or host.endswith("twitter.com"):
        return {"kind": "x", "label": "X video or post", "url": raw}
    if host.endswith("kick.com"):
        return {"kind": "kick", "label": "Kick stream", "url": raw}
    if host.endswith("dropbox.com"):
        q = parse_qs(p.query)
        q["dl"] = ["1"]
        direct = urlunparse(p._replace(query=urlencode(q, doseq=True)))
        return {"kind": "cloud", "label": "Dropbox shared link", "url": raw, "direct_url": direct}
    if host.endswith("drive.google.com"):
        q = parse_qs(p.query)
        file_id = (q.get("id") or [None])[0]
        if not file_id:
            m = re.search(r"/file/d/([^/]+)", p.path)
            file_id = m.group(1) if m else None
        direct = f"https://drive.google.com/uc?export=download&id={file_id}" if file_id else raw
        return {"kind": "cloud", "label": "Google Drive shared link", "url": raw, "direct_url": direct}
    path = p.path.lower().split("?")[0]
    if path.endswith(VIDEO_EXTS):
        return {"kind": "direct", "label": "Direct video file", "url": raw, "direct_url": raw}
    return {"kind": "webpage", "label": "Web link", "url": raw}

def youtube_metadata(url):
    try:
        r = requests.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=12)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}

def get_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(out.strip())

def download_direct(url, target):
    headers = {"User-Agent": "ClipForgeAI/2.0"}
    with requests.get(url, stream=True, timeout=(20, 45), allow_redirects=True, headers=headers) as r:
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        final_path = urlparse(r.url).path.lower()
        looks_video = ctype.startswith("video/") or final_path.endswith(VIDEO_EXTS)
        if not looks_video:
            raise ValueError(
                f"The link returned '{ctype or 'unknown content'}', not a video file. "
                "It may be a webpage, login screen, or sharing page. Use a direct video-file URL or upload the file."
            )
        limit = 1024 * 1024 * 1024
        total = 0
        with open(target, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    total += len(chunk)
                    if total > limit:
                        raise ValueError("This build has a 1 GB per-video download limit.")
                    f.write(chunk)
    if Path(target).stat().st_size < 100_000:
        raise ValueError("The downloaded file is too small to be a valid video.")

def transcribe_video(path, model_name, language):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    opts = {"vad_filter": True}
    if language != "Auto-detect":
        opts["language"] = language
    segments, info = model.transcribe(str(path), **opts)
    rows = []
    for s in segments:
        txt = (s.text or "").strip()
        if txt:
            rows.append({"start": float(s.start), "end": float(s.end), "text": txt})
    return rows, info.language

def score_text(text):
    t = text.lower()
    cues = [
        "wow", "wait", "no way", "amazing", "incredible", "crazy", "secret",
        "finally", "actually", "but then", "you won't believe", "the best",
        "worst", "never", "always", "important", "listen", "look at",
        "πραγματικά", "απίστευτο", "περίμενε", "τέλειο", "γιατί", "τελικά",
        "σημαντικό", "προσέξτε"
    ]
    return (min(len(t) / 150, 1.4)
            + sum(0.9 for phrase in cues if phrase in t)
            + min(text.count("!") * .3, 1.0)
            + min(text.count("?") * .12, .5))

def suggest_clips(segments, total_duration, clip_len, wanted):
    if not segments:
        raise ValueError("No speech was detected. Try another video or use manual trimming.")
    stride = max(4.0, clip_len * .3)
    starts = []
    pos = 0.0
    while pos < max(1.0, total_duration - clip_len + 1):
        starts.append(pos)
        pos += stride
    if not starts:
        starts = [0.0]
    ranked = []
    for start in starts:
        end = min(total_duration, start + clip_len)
        group = [s for s in segments if s["end"] > start and s["start"] < end]
        if not group:
            continue
        text = " ".join(s["text"] for s in group)
        speech = sum(max(0, min(s["end"], end) - max(s["start"], start)) for s in group)
        score = score_text(text) + min(speech / clip_len, 1)
        ranked.append({"score": score, "start": start, "end": end, "text": text})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    selected = []
    for item in ranked:
        if all(abs(item["start"] - chosen["start"]) > clip_len * .65 for chosen in selected):
            selected.append(item)
        if len(selected) >= wanted:
            break
    return sorted(selected, key=lambda x: x["start"])

def srt_time(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def write_srt(segments, start, end, output):
    lines, idx = [], 1
    for seg in segments:
        a, b = max(start, seg["start"]), min(end, seg["end"])
        if b <= a:
            continue
        lines.append(f"{idx}\n{srt_time(a-start)} --> {srt_time(b-start)}\n{seg['text']}\n")
        idx += 1
    Path(output).write_text("\n".join(lines), encoding="utf-8")

def render_clip(source, start, end, out, aspect, burn_subs, segments):
    if end <= start:
        raise ValueError("End time must be after start time.")
    if aspect == "9:16":
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    elif aspect == "1:1":
        vf = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    else:
        vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    if burn_subs:
        srt = str(Path(out).with_suffix(".srt"))
        write_srt(segments, start, end, srt)
        escaped = srt.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf += f",subtitles='{escaped}'"
    run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{end-start:.3f}",
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])

def init_state():
    defaults = {"source_path": None, "source_name": None, "transcript": [], "clips": [],
                "link_info": None, "yt_meta": {}, "detected_language": None}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
init_state()

# ------------------------------ Sidebar ------------------------------------
with st.sidebar:
    st.markdown("## ⚙️ Workspace settings")
    clip_len = st.slider("Target clip length", 15, 90, 35, 5)
    clip_count = st.slider("Number of clips", 1, 10, 5)
    aspect = st.selectbox("Output format", ["9:16 · Shorts / Reels / TikTok", "1:1 · Square", "16:9 · Landscape"])
    aspect_key = aspect.split(" ")[0]
    model_name = st.selectbox("Speech model", ["tiny", "base", "small"], index=1)
    language = st.selectbox("Audio language", ["Auto-detect", "en", "el", "es", "fr", "de", "it", "pt"])
    burn_subs = st.checkbox("Burn subtitles into clips", True)
    st.markdown("---")
    st.caption("AI suggestions use speech transcription and transcript scoring. Review clips before posting.")

# ------------------------------ Link intake --------------------------------
st.markdown('<div class="section-title">01 · Add a video</div>', unsafe_allow_html=True)
link_col, button_col = st.columns([5, 1.2], vertical_alignment="bottom")
with link_col:
    pasted_link = st.text_input("Paste a video link", placeholder="YouTube, Twitch, TikTok, Instagram, Vimeo, Dropbox, Drive, direct MP4…", label_visibility="collapsed")
with button_col:
    resolve_clicked = st.button("Check link", type="primary", use_container_width=True)

if resolve_clicked:
    info = identify_link(pasted_link)
    st.session_state.link_info = info
    st.session_state.yt_meta = {}
    if info["kind"] == "youtube" and info.get("video_id"):
        st.session_state.yt_meta = youtube_metadata(info["url"])
    if info["kind"] in ("direct", "cloud"):
        try:
            target = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
            with st.spinner("Checking and retrieving the video file…"):
                download_direct(info.get("direct_url", info["url"]), target)
            st.session_state.source_path = target
            st.session_state.source_name = info["label"]
            st.session_state.transcript = []
            st.session_state.clips = []
            st.success("Video file loaded. You can run AI clipping below.")
        except Exception as e:
            st.error(str(e))

if st.session_state.link_info:
    info = st.session_state.link_info
    if info["kind"] == "youtube":
        meta = st.session_state.yt_meta
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        c1, c2 = st.columns([1.2, 3])
        with c1:
            if info.get("video_id"):
                st.image(f"https://img.youtube.com/vi/{info['video_id']}/hqdefault.jpg", use_container_width=True)
        with c2:
            st.markdown("**YouTube link recognised**")
            st.write(meta.get("title", "Video link detected"))
            st.caption(meta.get("author_name", "YouTube") + " · Preview and metadata only")
            st.link_button("Open video on YouTube", info["url"])
            st.info("YouTube watch links cannot be downloaded for processing by this app. Upload a video file you are authorised to edit, or use an approved source integration.")
        st.markdown('</div>', unsafe_allow_html=True)
    elif info["kind"] == "twitch":
        st.info("Twitch link recognised. This build can open the stream/VOD, but processing its video requires an authorised Twitch integration or an eligible source file.")
        st.link_button("Open on Twitch", info["url"])
    elif info["kind"] in ("tiktok", "instagram", "vimeo", "facebook", "x", "kick"):
        st.info(f"{info['label']} recognised. The link is accepted and can be opened, but a platform page is not a direct video file. Processing requires an authorised integration or a video file you can provide.")
        st.link_button("Open source link", info["url"])
    elif info["kind"] == "webpage":
        st.warning("This is a webpage link, not a direct video file. If the site provides a direct MP4/MOV/WebM link, paste that instead.")
        st.link_button("Open link", info["url"])
    elif info["kind"] == "invalid":
        st.error(info["label"])

st.markdown('<div class="muted">Recognises YouTube · Twitch · TikTok · Instagram · Vimeo · Facebook · X · Kick · Dropbox · Google Drive · direct video files</div>', unsafe_allow_html=True)

st.markdown("---")
st.markdown('<div class="section-title">Or upload a video</div>', unsafe_allow_html=True)
upload_col, load_col = st.columns([4, 1.2], vertical_alignment="bottom")
with upload_col:
    upload = st.file_uploader("Choose a video", type=["mp4", "mov", "m4v", "webm", "mkv", "avi"], label_visibility="collapsed")
with load_col:
    load_upload = st.button("Load upload", use_container_width=True)
if load_upload:
    if upload is None:
        st.warning("Choose a video first.")
    else:
        suffix = Path(upload.name).suffix or ".mp4"
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp.write(upload.getbuffer())
        temp.close()
        st.session_state.source_path = temp.name
        st.session_state.source_name = upload.name
        st.session_state.transcript = []
        st.session_state.clips = []
        st.success(f"Loaded {upload.name}")

# ------------------------------ Loaded video -------------------------------
if st.session_state.source_path and Path(st.session_state.source_path).exists():
    st.markdown("---")
    st.markdown('<div class="section-title">02 · AI clipping studio</div>', unsafe_allow_html=True)
    try:
        duration = get_duration(st.session_state.source_path)
        stat1, stat2, stat3 = st.columns(3)
        with stat1:
            st.markdown(f'<div class="stat"><div class="num">{duration/60:.1f} min</div><div class="lab">VIDEO LENGTH</div></div>', unsafe_allow_html=True)
        with stat2:
            st.markdown(f'<div class="stat"><div class="num">{clip_count}</div><div class="lab">TARGET CLIPS</div></div>', unsafe_allow_html=True)
        with stat3:
            st.markdown(f'<div class="stat"><div class="num">{aspect_key}</div><div class="lab">OUTPUT RATIO</div></div>', unsafe_allow_html=True)
        with st.expander("Preview source video", expanded=True):
            st.video(st.session_state.source_path)
        can_run = ffmpeg_ok()
        if not can_run:
            st.error("FFmpeg is not installed on the server. Add it using packages.txt and redeploy.")
        if st.button("✨ Find my best moments", type="primary", use_container_width=True, disabled=not can_run):
            try:
                with st.spinner("Transcribing audio and ranking highlight moments… The first run may take a few minutes."):
                    transcript, detected = transcribe_video(st.session_state.source_path, model_name, language)
                    st.session_state.transcript = transcript
                    st.session_state.detected_language = detected
                    st.session_state.clips = suggest_clips(transcript, duration, clip_len, clip_count)
                st.success(f"Found {len(st.session_state.clips)} suggested moments · detected language: {detected}")
            except Exception as e:
                st.error(f"AI analysis failed: {e}")
    except Exception as e:
        st.error(f"Could not read the video: {e}")

# ------------------------------ Review / export ----------------------------
if st.session_state.clips:
    st.markdown("---")
    st.markdown('<div class="section-title">03 · Review and export</div>', unsafe_allow_html=True)
    export_items = []
    for i, clip in enumerate(st.session_state.clips, 1):
        start, end = float(clip["start"]), float(clip["end"])
        with st.expander(f"Clip {i:02d}  ·  {int(start//60):02}:{int(start%60):02} – {int(end//60):02}:{int(end%60):02}", expanded=(i == 1)):
            st.write(clip["text"][:900] + ("…" if len(clip["text"]) > 900 else ""))
            a, b = st.columns(2)
            with a:
                edited_start = st.number_input("Start (seconds)", min_value=0.0, max_value=float(get_duration(st.session_state.source_path)),
                                               value=start, step=0.5, key=f"start_{i}")
            with b:
                edited_end = st.number_input("End (seconds)", min_value=0.5, max_value=float(get_duration(st.session_state.source_path)),
                                             value=end, step=0.5, key=f"end_{i}")
            if st.button(f"Render clip {i}", key=f"render_{i}", use_container_width=True):
                try:
                    output = tempfile.NamedTemporaryFile(delete=False, suffix=f"_clip_{i}.mp4").name
                    with st.spinner("Rendering MP4…"):
                        render_clip(st.session_state.source_path, edited_start, edited_end, output,
                                    aspect_key, burn_subs, st.session_state.transcript)
                    data = Path(output).read_bytes()
                    st.video(data)
                    st.download_button("⬇ Download MP4", data=data, file_name=f"clipforge_clip_{i}.mp4",
                                       mime="video/mp4", key=f"download_{i}")
                except Exception as e:
                    st.error(f"Could not render this clip: {e}")

st.markdown("---")
with st.expander("Supported links, privacy and limitations"):
    st.markdown("""
    **Direct processing:** uploaded video files, public direct video-file URLs, and some public cloud share links that resolve to an actual video response.

    **Recognised but not directly extracted:** YouTube, Twitch, TikTok, Instagram, Vimeo, Facebook, X and Kick page links. These platforms may require official API access, account authorisation, creator permissions or an exported source file.

    **AI behaviour:** speech is transcribed with the open-source Whisper model. Suggested moments are ranked using transcript cues and speech coverage. This is an automated first pass, not a promise that a clip will go viral. Review before posting.

    **Privacy:** files are temporarily stored on the app server during processing. Avoid uploading private or sensitive videos to a service you do not control.
    """)
st.caption("ClipForge AI · Community build · Use source videos you are authorised to process.")
