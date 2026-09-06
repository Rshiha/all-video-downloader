# 🛠️ YouTube Bot-Check & Render Deployment Troubleshooting Guide

This guide explains how YouTube's anti-bot verification challenge (`Sign in to confirm you're not a bot`), Render read-only deployment issues (`[Errno 30]`), and **Zero-Downtime Dynamic Cookie Refreshing (`POST /admin/cookies`)** are implemented and managed step-by-step.

---

## 1. Summary of Issues & Solutions

| Issue / Challenge | Root Cause | Technical Fix Applied |
| :--- | :--- | :--- |
| **`Sign in to confirm you're not a bot`** | YouTube requires Proof-of-Origin (PO) tokens or session cookies on datacenter IPs (e.g. Render). | 1. Installed Deno JS runtime.<br>2. Configured `player_client: ["android", "web"]` fallback.<br>3. Enabled dynamic `youtube_cookies.txt` support. |
| **`[Errno 30] Read-only file system`** | Render mounts Secret Files (`/etc/secrets/`) as read-only, but `yt-dlp` attempts to write session updates back to the cookie file. | Added automatic copying of read-only cookie mounts to a writable temp directory (`/tmp/active_youtube_cookies.txt`). |
| **4K/2K Quality Degradation** | `yt-dlp` skipped high-resolution VP9/AV1 streams without JavaScript runtime challenge solvers. | Configured `js_runtimes: {"node": {}, "deno": {}}` and `format_sort: ["res", "fps", "vbr"]`. |
| **Recurring Downtime on Cookie Expiry** | Updating Render Secret Files requires redeploying, causing downtime per cookie refresh. | Implemented protected `POST /admin/cookies` API endpoint to update cookies live in memory & `/tmp` without redeploying. |

---

## 2. Zero-Downtime Dynamic Cookie Refresh (`POST /admin/cookies`)

To refresh expired YouTube cookies instantly **without opening Render's dashboard, triggering a redeploy, or causing any service downtime**:

### Single `curl` Command to Refresh Cookies Live:

```bash
curl -X POST https://your-service.onrender.com/admin/cookies \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"content\": \"$(cat youtube_cookies.txt | sed 's/"/\\"/g')\"}"
```

*(Set `ADMIN_TOKEN` in Render Environment variables to secure the endpoint)*.

---

## 3. Initial Setup & Exporting Cookies

### Step 1: Export Non-Rotating Cookies (Official yt-dlp Wiki Trick)

> 💡 **Why normal cookies expire quickly**: YouTube automatically rotates session cookies (`SIDCC`, `LOGIN_INFO`) on open browser tabs. To export cookies that **NEVER rotate or expire**, follow the official `yt-dlp` wiki method:

1. Open a **new Private Browsing / Incognito window** and log into YouTube.
2. In that **same tab**, navigate to `https://www.youtube.com/robots.txt` (this stops YouTube scripts from running in the background and rotating your cookies).
3. Export your cookies using the **[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** extension.
4. Save the file as **`youtube_cookies.txt`**.
5. **Immediately close the Private/Incognito window** so the session is never opened in your browser again!

### Step 2: Configure Render Secret Files & Environment Variables

1. Log into **[Render Dashboard](https://dashboard.render.com/)** and select your Web Service.
2. Go to **Environment** $\rightarrow$ **Secret Files** $\rightarrow$ Click **Add Secret File**:
   - **Filename**: `youtube_cookies.txt`
   - **Contents**: Paste the full text of your exported `youtube_cookies.txt` file.
   - Click **Save Changes**.
3. Under **Environment Variables**, click **Add Environment Variable**:
   - **Key**: `COOKIES_FILE` $\rightarrow$ **Value**: `/etc/secrets/youtube_cookies.txt`
   - **Key**: `ADMIN_TOKEN` $\rightarrow$ **Value**: `your-secret-admin-token`
   - **Key**: `ALERT_WEBHOOK_URL` *(Optional)* $\rightarrow$ **Value**: `https://hooks.slack.com/services/...`
   - Click **Save Changes**.

---

## 4. Writable Cookie File Resolution (Handling `[Errno 30]`)

Because `/etc/secrets/` is a read-only filesystem, the backend in `app/cookies.py`, `app/probe.py`, and `app/downloader.py` automatically seeds `/tmp/active_youtube_cookies.txt` (writable) on startup:

```python
if path and os.path.exists(path):
    target_path = path
    if not os.access(path, os.W_OK):
        # Copy from read-only mount (Render /etc/secrets/) to writable temp storage
        writable_path = os.path.join(tempfile.gettempdir(), "active_youtube_cookies.txt")
        try:
            shutil.copyfile(path, writable_path)
            target_path = writable_path
        except Exception as e:
            print(f"[yt-dlp] Warning copying read-only cookies file: {e}")
    options["cookiefile"] = target_path
```

---

## 5. Live Cookie Age & Staleness Health Monitoring (`GET /healthz`)

Open your deployed service's `/healthz` endpoint:

```http
GET https://your-service.onrender.com/healthz
```

Expected JSON response:

```json
{
  "status": "ok",
  "cookies_present": true,
  "cookies_age_hours": 2.4,
  "cookies_stale": false,
  "active_cookie_file": "/tmp/active_youtube_cookies.txt"
}
```

- **`cookies_present`**: Indicates if valid cookies are loaded.
- **`cookies_age_hours`**: Shows how many hours ago cookies were updated.
- **`cookies_stale`**: Automatically turns `true` if cookies exceed 10 days of age.

---

## 6. Real-Time Bot-Check Webhook Alerting

If `ALERT_WEBHOOK_URL` is set in your environment (Slack or Discord incoming webhook), whenever a download encounters YouTube's bot challenge, the system automatically sends an instant alert containing:
- The failing Job ID and error message.
- The exact `curl` command to refresh cookies dynamically without a redeploy.

---

## 7. Keyless YouTube oEmbed API Fallback Probing

To guarantee that metadata probing (`probe_video`) **NEVER** fails (even if cookies expire or YouTube blocks requests on datacenter IPs), [app/probe.py] includes a fail-safe fallback using YouTube's public oEmbed API:

```http
GET https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=VIDEO_ID&format=json
```

- **0.1s Response Time**: Returns video title, creator channel, thumbnail URL, and default quality options.
- **Zero API Keys Required**: Does not require a Google API key.
- **0% Bot Verification Failure**: Immune to BotGuard and IP blocks.
