import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional, List

try:
    from .jobs import JOBS, new_job, get_job
    from .downloader import run_download
    from .probe import probe_video, ALLOWED_HOSTS
except ImportError:
    from jobs import JOBS, new_job, get_job
    from downloader import run_download
    from probe import probe_video, ALLOWED_HOSTS

app = FastAPI(title="Media Downloader API", version="1.0.0")

import shutil
import tempfile
import time
from fastapi import Header

try:
    from .cookies import COOKIES_PATH, get_cookies_path, update_cookies, cookies_age_seconds
except ImportError:
    from cookies import COOKIES_PATH, get_cookies_path, update_cookies, cookies_age_seconds

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "secret-admin-token")

@app.on_event("startup")
def startup_cookies_log():
    # Seed active cookies from Secret File or environment if active cookies do not exist
    seed_file = os.environ.get("COOKIES_FILE", "/etc/secrets/youtube_cookies.txt")
    if not get_cookies_path() and seed_file and os.path.exists(seed_file):
        try:
            shutil.copyfile(seed_file, COOKIES_PATH)
            print(f"[startup] Seeded active cookies from {seed_file}")
        except Exception as e:
            print(f"[startup seed error] {e}")

    active = get_cookies_path()
    print(f"[startup] Active cookies file: '{active}', exists={bool(active)}")

    # Clean up orphaned temporary files older than 1 hour from temp directory
    try:
        temp_dir = os.path.join(tempfile.gettempdir(), "yt_downloads")
        if os.path.exists(temp_dir):
            now = time.time()
            for f in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, f)
                if os.path.isfile(file_path) and (now - os.path.getmtime(file_path)) > 3600:
                    try:
                        os.remove(file_path)
                        print(f"[cleanup] Removed orphaned temp file: {f}")
                    except Exception:
                        pass
    except Exception as e:
        print(f"[startup cleanup error] {e}")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProbeRequest(BaseModel):
    url: HttpUrl

class DownloadRequest(BaseModel):
    url: HttpUrl
    format: str = "mp4"       # mp4 | mp3
    quality: str = "720"      # 1080 | 720 | 480 | 360
    bitrate: str = "192"      # 320 | 256 | 192 | 128

class RefreshCookiesRequest(BaseModel):
    content: str

@app.get("/healthz")
def healthz():
    age = cookies_age_seconds()
    return {
        "status": "ok",
        "cookies_present": age is not None,
        "cookies_age_hours": round(age / 3600, 1) if age is not None else None,
        "cookies_stale": age is not None and age > (60 * 60 * 24 * 10),  # >10 days
        "active_cookie_file": get_cookies_path(),
    }

@app.post("/admin/cookies")
def refresh_cookies(req: RefreshCookiesRequest, x_admin_token: str = Header(...)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Admin Token")
    content = req.content.strip()
    if not content or "youtube.com" not in content:
        raise HTTPException(status_code=400, detail="Invalid cookies.txt content (must contain youtube.com)")
    meta = update_cookies(content)
    return {"status": "updated", **meta}

@app.post("/api/probe")
def probe_endpoint(req: ProbeRequest):
    host = req.url.host or ""
    if host.lower() not in ALLOWED_HOSTS:
        raise HTTPException(status_code=400, detail="Only YouTube URLs are supported")
    try:
        data = probe_video(str(req.url))
        if not data:
            raise HTTPException(status_code=404, detail="Could not extract video metadata")
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/jobs")
def create_job(req: DownloadRequest, bg: BackgroundTasks):
    host = req.url.host or ""
    if host.lower() not in ALLOWED_HOSTS:
        raise HTTPException(status_code=400, detail="Only YouTube URLs are supported (youtube.com, youtu.be)")

    job = new_job(format_choice=req.format, quality=req.quality)
    bg.add_task(run_download, job.id, str(req.url), req.format, req.quality, req.bitrate)
    return {"job_id": job.id}

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "title": job.title,
        "duration": job.duration,
        "format": job.format,
        "quality": job.quality,
        "is_playlist": job.is_playlist,
        "playlist_index": job.playlist_index,
        "playlist_count": job.playlist_count,
        "current_video_title": job.current_video_title,
        "has_file": bool(job.filepath and os.path.exists(job.filepath))
    }

@app.get("/api/jobs/{job_id}/file")
def get_file(job_id: str, bg: BackgroundTasks):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done" or not job.filepath or not os.path.exists(job.filepath):
        raise HTTPException(status_code=404, detail="File not ready or unavailable")

    filepath = job.filepath
    filename = os.path.basename(filepath)

    def cleanup():
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
        JOBS.pop(job_id, None)

    bg.add_task(cleanup)
    return FileResponse(path=filepath, filename=filename, media_type="application/octet-stream")

# Mount static files directory if present (serves built React frontend)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if not os.path.exists(static_dir):
    static_dir = "static"

if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
