import os
import tempfile
import hashlib
import time
from typing import Optional, Dict, Any

COOKIES_PATH = os.path.join(tempfile.gettempdir(), "active_youtube_cookies.txt")
COOKIES_META_PATH = COOKIES_PATH + ".meta"

def get_cookies_path() -> Optional[str]:
    if os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 0:
        return COOKIES_PATH
    return None

def update_cookies(content: str) -> Dict[str, Any]:
    with open(COOKIES_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    meta = {
        "updated_at": time.time(),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()[:12],
        "size": len(content),
    }
    with open(COOKIES_META_PATH, "w", encoding="utf-8") as f:
        f.write(str(meta))
    return meta

def cookies_age_seconds() -> Optional[float]:
    if not os.path.exists(COOKIES_PATH):
        return None
    return time.time() - os.path.getmtime(COOKIES_PATH)
