import os, re, uuid, shutil, socket, ipaddress
from urllib.parse import urlparse
from flask import Flask, request, render_template, send_file, jsonify
import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = "/tmp/avd"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def valid_url(raw):
    try:
        p = urlparse(raw.strip())
        if p.scheme not in ("http", "https") or not p.netloc:
            return False
        host = p.hostname
        if not host:
            return False
        # Basic SSRF protection for direct IP/localhost targets.
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            if host.lower() in {"localhost", "localhost.localdomain"}:
                return False
        return True
    except Exception:
        return False

@app.get("/")
def home():
    return render_template("index.html")

@app.post("/download")
def download():
    url = (request.form.get("url") or "").strip()
    mode = request.form.get("mode", "video")
    quality = request.form.get("quality", "best")
    if not valid_url(url):
        return jsonify(error="Valid public http/https video URL দিন।"), 400

    job = uuid.uuid4().hex
    outtmpl = os.path.join(DOWNLOAD_DIR, job, "%(title).120B-%(id)s.%(ext)s")
    workdir = os.path.dirname(outtmpl)
    os.makedirs(workdir, exist_ok=True)

    # This downloader never adds a watermark.
    # It does NOT remove embedded watermarks from source videos.
    if mode == "audio":
        fmt = "bestaudio/best"
        postprocessors = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        if quality == "720":
            fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        elif quality == "480":
            fmt = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        else:
            fmt = "bestvideo+bestaudio/best"
        postprocessors = [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }]

    opts = {
        "outtmpl": outtmpl,
        "format": fmt,
        "merge_output_format": "mp4" if mode != "audio" else None,
        "postprocessors": postprocessors,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
           "max_filesize": 1024 * 1024 * 1024,
        "cookiefile": "m.youtube.com_cookies.txt",
 }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared = ydl.prepare_filename(info)
        candidates = []
        for root, _, files in os.walk(workdir):
            for f in file:
                candidates.append(os.path.join(root, f))
        if not candidates:
            raise RuntimeError("Download file তৈরি হয়নি।")
        path = max(candidates, key=os.path.getsize)
        ext = ".mp3" if mode == "audio" else ".mp4"
        download_name = re.sub(r'[^A-Za-z0-9._ -]+', '_', os.path.basename(path))
        if not download_name.lower().endswith(ext):
            download_name = os.path.splitext(download_name)[0] + ext
        return send_file(path, as_attachment=True, download_name=download_name)
    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        return jsonify(error=str(e)[:700]), 500

@app.get("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
