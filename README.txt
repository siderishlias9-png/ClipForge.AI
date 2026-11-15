CLIPFORGE AI — UPDATED LINK-AWARE BUILD

FILES
- app.py: Streamlit application
- requirements.txt: Python packages
- packages.txt: FFmpeg system dependency

FEATURES
- Redesigned responsive dark interface
- Recognises YouTube, Twitch, TikTok, Instagram, Vimeo, Facebook, X, Kick,
  Dropbox, Google Drive and direct video-file links
- YouTube title/thumbnail metadata preview where available
- Direct video-file download and processing
- Video upload fallback
- Whisper speech transcription
- Transcript-based highlight suggestions
- Adjustable clip start/end
- MP4 export in 9:16, 1:1 and 16:9 with optional burned-in subtitles

IMPORTANT LINK LIMITS
Platform page URLs are identified but are not extracted or downloaded.
YouTube/Twitch/TikTok/Instagram/Vimeo/Facebook/X/Kick links may require official
API integrations, account authorisation, creator permissions, or an exported
source file. The app does not bypass DRM, logins, access controls or platform
restrictions. A direct URL must return a video file, not an HTML webpage.

RUN LOCALLY
1. Install Python 3.10+ and FFmpeg (ffmpeg and ffprobe on PATH).
2. In this folder run: pip install -r requirements.txt
3. Run: streamlit run app.py

STREAMLIT COMMUNITY CLOUD
1. Upload these four files to the root of your GitHub repository.
2. Create an app at https://share.streamlit.io/
3. Select the repository, main branch, and app.py.
4. packages.txt installs FFmpeg on supported Streamlit Cloud builds.

LIMITATIONS
Free hosting has CPU, memory, request-size and execution-time limits.
The first Whisper model run downloads the selected model. AI ranking is a
transcript-based suggestion, not semantic video understanding or a virality guarantee.
