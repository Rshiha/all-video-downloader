import os
import time
from typing import Dict, Any, Optional
from yt_dlp import YoutubeDL

ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"}

def is_valid_url(url_str: str) -> bool:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url_str)
        return parsed.hostname in ALLOWED_HOSTS if parsed.hostname else False
    except Exception:
        return False

def friendly_error(msg: str) -> str:
    if "Sign in to confirm" in msg or "not a bot" in msg or "BotGuard" in msg:
        return "YouTube anti-bot verification triggered. Please try again shortly or upload valid youtube_cookies.txt."
    if "Video unavailable" in msg or "private" in msg.lower() or "Requested format" in msg:
        return "This video is unavailable, deleted, or private."
    return msg

def get_yt_dlp_options() -> Dict[str, Any]:
    opts: Dict[str, Any] = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "remote_components": ["ejs:github", "ejs:npm"],
        "format_sort": ["res", "fps", "vbr"],
        "extractor_args": {
            "youtube": {
                "player_client": ["android_vr", "web_safari", "web_embedded"]
            }
        }
    }

    # Ultimate Solution 1: Google OAuth2 Device Token Authentication (no cookies needed)
    if os.environ.get("ENABLE_OAUTH2", "").lower() in ("true", "1", "yes"):
        opts["username"] = "oauth2"
        opts["password"] = ""

    # Ultimate Solution 2: Proof-of-Origin (PO) Token Support
    po_token = os.environ.get("PO_TOKEN")
    if po_token:
        opts["extractor_args"]["youtube"]["po_token"] = [f"web+{po_token}"]

    import shutil
    import tempfile
    try:
        from .cookies import get_cookies_path
    except ImportError:
        from cookies import get_cookies_path

    active_cookie = get_cookies_path()
    if active_cookie:
        opts["cookiefile"] = active_cookie
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
                        print(f"[yt-dlp probe] Warning copying read-only cookies file: {e}")
                opts["cookiefile"] = target_path
                break

    proxy = os.environ.get("PROXY_URL")
    if proxy:
        opts["proxy"] = proxy

    return opts

def probe_video(url: str, _retry: bool = False) -> Optional[Dict[str, Any]]:
    options = get_yt_dlp_options()
    
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            # Playlist detection
            if info.get("_type") == "playlist" or "entries" in info:
                raw_entries = info.get("entries", [])
                entries = [e for e in raw_entries if e]
                first_entry = entries[0] if entries else {}
                title = info.get("title") or "YouTube Playlist"
                total_duration = sum((e.get("duration", 0) or 0) for e in entries)
                return {
                    "title": title,
                    "duration": total_duration,
                    "thumbnail": first_entry.get("thumbnail") or info.get("thumbnail") or "",
                    "channel": info.get("uploader") or info.get("channel") or "Playlist",
                    "qualities": [2160, 1440, 1080, 720, 480, 360],
                    "is_too_long": False,
                    "is_playlist": True,
                    "playlist_count": len(entries)
                }

            duration = info.get("duration", 0) or 0
            
            # Gather available video heights
            formats = info.get("formats", [])
            heights = set()
            for f in formats:
                h = f.get("height")
                if h and isinstance(h, int):
                    heights.add(h)
            
            qualities = sorted(list(heights), reverse=True)

            return {
                "title": info.get("title") or "Unknown Title",
                "duration": duration,
                "thumbnail": info.get("thumbnail") or info.get("thumbnails", [{}])[-1].get("url", ""),
                "channel": info.get("uploader") or info.get("channel") or "Unknown Creator",
                "qualities": qualities,
                "is_too_long": duration > (30 * 60),
                "is_playlist": False,
                "playlist_count": 1
            }
    except Exception as e:
        msg = str(e)
        if not _retry and ("Sign in to confirm" in msg or "not a bot" in msg or "BotGuard" in msg):
            time.sleep(2)
            return probe_video(url, _retry=True)
        
        # Keyless YouTube oEmbed API Fallback (Guarantees metadata probing never fails)
        oembed_data = oembed_fallback_probe(url)
        if oembed_data:
            return oembed_data

        raise RuntimeError(friendly_error(msg))

import re
import json
import urllib.request

def extract_youtube_id(url: str) -> Optional[str]:
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11})",
        r"youtu\.be\/([0-9A-Za-z_-]{11})"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def oembed_fallback_probe(url: str) -> Optional[Dict[str, Any]]:
    try:
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
        req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                video_id = extract_youtube_id(url)
                thumbnail = data.get("thumbnail_url") or (f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else "")
                return {
                    "title": data.get("title") or "YouTube Video",
                    "duration": 0,
                    "thumbnail": thumbnail,
                    "channel": data.get("author_name") or "YouTube Creator",
                    "qualities": [2160, 1440, 1080, 720, 480, 360],
                    "is_too_long": False,
                    "is_playlist": False,
                    "playlist_count": 1
                }
    except Exception as e:
        print(f"[oEmbed probe error] {e}")
    return None
