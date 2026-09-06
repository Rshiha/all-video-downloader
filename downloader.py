import os
import tempfile
import time
from typing import Dict, Any
from yt_dlp import YoutubeDL
try:
    from .jobs import JOBS
except ImportError:
    from jobs import JOBS

# Use system temp directory or /tmp/downloads (ephemeral storage)
SYSTEM_TEMP = tempfile.gettempdir()
DOWNLOAD_DIR = os.path.join(SYSTEM_TEMP, "yt_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_DURATION_SECONDS = 30 * 60  # 30 minute cap to survive 512MB RAM free tier limits

def friendly_error(msg: str, job_id: str = "") -> str:
    if "Sign in to confirm" in msg or "not a bot" in msg or "BotGuard" in msg:
        try:
            from .alerting import alert_cookie_failure
        except ImportError:
            from alerting import alert_cookie_failure
        alert_cookie_failure(job_id, msg)
        return "YouTube anti-bot verification triggered. Please try again in a few moments or ensure cookies.txt is updated."
    if "Video unavailable" in msg or "private" in msg.lower() or "Requested format" in msg:
        return "This video is unavailable, deleted, or private."
    if "setdefault" in msg:
        return "Video stream format unavailable or restricted by YouTube."
    return msg

def run_download(job_id: str, url: str, format_choice: str, quality: str, bitrate: str, _retry: bool = False):
    job = JOBS.get(job_id)
    if not job:
        return

    job.status = "downloading"
    job.progress = 0.0

    def hook(d: Dict[str, Any]):
        info = d.get("info_dict", {})
        if info:
            if info.get("playlist_index"):
                job.is_playlist = True
                job.playlist_index = info.get("playlist_index")
                job.playlist_count = info.get("playlist_count") or job.playlist_count or 1
            if info.get("title"):
                job.current_video_title = info.get("title")

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total and total > 0:
                single_progress = min(100.0, max(0.0, (downloaded / total) * 100))
                if job.is_playlist and job.playlist_count > 0:
                    overall = ((max(0, job.playlist_index - 1) + (single_progress / 100.0)) / job.playlist_count) * 100.0
                    job.progress = round(min(99.0, max(0.0, overall)), 1)
                else:
                    job.progress = round(single_progress, 1)
        elif d["status"] == "finished":
            job.status = "converting"
            if not job.is_playlist:
                job.progress = 99.0

    outtmpl_pattern = os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s")

    options: Dict[str, Any] = {
        "outtmpl": outtmpl_pattern,
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "remote_components": ["ejs:github", "ejs:npm"],
        "format_sort": ["res", "fps", "vbr"],
        "extractor_args": {
            "youtube": {
                "player_client": ["android_vr", "web_safari", "web_embedded"]
            }
        },
        # Resumable Download Strategy (Native yt-dlp resume & partial file protection)
        "continuedl": True,
        "part": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        # Performance & Network Optimization (Parallel fragments, chunked I/O)
        "concurrent_fragment_downloads": 3,
        "http_chunk_size": 10485760,
        "buffersize": 1024 * 64,
        "socket_timeout": 30,
    }

    # Ultimate Solution 1: Google OAuth2 Device Token Authentication (no cookies needed)
    if os.environ.get("ENABLE_OAUTH2", "").lower() in ("true", "1", "yes"):
        options["username"] = "oauth2"
        options["password"] = ""

    # Ultimate Solution 2: Proof-of-Origin (PO) Token Support
    po_token = os.environ.get("PO_TOKEN")
    if po_token:
        options["extractor_args"]["youtube"]["po_token"] = [f"web+{po_token}"]

    import shutil
    try:
        from .cookies import get_cookies_path
    except ImportError:
        from cookies import get_cookies_path

    active_cookie = get_cookies_path()
    if active_cookie:
        options["cookiefile"] = active_cookie
    else:
        # Support COOKIES_FILE env var, Render Secret Files (/etc/secrets/youtube_cookies.txt), or local files
        cookie_paths = [
            os.environ.get("COOKIES_FILE", ""),
            os.environ.get("COOKIES_PATH", ""),
            "/etc/secrets/youtube_cookies.txt",
            "youtube_cookies.txt",
            "cookies.txt",
            "/app/cookies.txt"
        ]
        for path in cookie_paths:
            if path and os.path.exists(path):
                target_path = path
                if not os.access(path, os.W_OK):
                    # Copy from read-only mount (Render /etc/secrets/) to writable temp directory
                    writable_path = os.path.join(tempfile.gettempdir(), "active_youtube_cookies.txt")
                    try:
                        shutil.copyfile(path, writable_path)
                        target_path = writable_path
                    except Exception as e:
                        print(f"[yt-dlp download] Warning copying read-only cookies file: {e}")
                options["cookiefile"] = target_path
                break

    proxy = os.environ.get("PROXY_URL")
    if proxy:
        options["proxy"] = proxy

    ffmpeg_loc = os.environ.get("FFMPEG_LOCATION")
    if ffmpeg_loc:
        options["ffmpeg_location"] = ffmpeg_loc

    if format_choice == "mp3":
        options["format"] = f"bestaudio[abr<={bitrate}]/bestaudio/best"
        options["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": bitrate,
        }]
        options["postprocessor_args"] = {
            "ffmpeg": ["-threads", "2"]
        }
    else:
        # Layered format selection (exact height -> best height fallback -> best)
        if quality == "best" or quality == "2160":
            options["format"] = "bestvideo+bestaudio/best"
        else:
            options["format"] = (
                f"bestvideo[height<={quality}]+bestaudio/"
                f"best[height<={quality}]/"
                f"best"
            )
        options["merge_output_format"] = "mp4"
        options["postprocessor_args"] = {
            "ffmpeg": ["-threads", "2", "-movflags", "+faststart"]
        }

    client_attempts = [None]  # None = default options["extractor_args"]
    if options.get("cookiefile"):
        client_attempts.append(["tv"])

    last_error = None
    for clients in client_attempts:
        attempt_options = dict(options)
        if clients:
            attempt_options["extractor_args"] = {"youtube": {"player_client": clients}}

        try:
            with YoutubeDL(attempt_options) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    continue
                filename = ydl.prepare_filename(info)
                
                if format_choice == "mp3":
                    base, _ = os.path.splitext(filename)
                    filename = base + ".mp3"
                elif not os.path.exists(filename):
                    base, _ = os.path.splitext(filename)
                    if os.path.exists(base + ".mp4"):
                        filename = base + ".mp4"

                if os.path.exists(filename):
                    job.filepath = filename
                    job.status = "done"
                    job.progress = 100.0
                    return
                else:
                    matched = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.startswith(job_id)]
                    if matched:
                        job.filepath = matched[0]
                        job.status = "done"
                        job.progress = 100.0
                        return
                    else:
                        raise RuntimeError("Downloaded file not found on disk.")
        except Exception as e:
            last_error = e
            continue

    job.status = "error"
    job.error = friendly_error(str(last_error), job_id)
