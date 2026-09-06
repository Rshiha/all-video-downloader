import os
from typing import Optional

ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL")  # Slack/Discord/Custom webhook URL

def alert_cookie_failure(job_id: str, error: str):
    if not ALERT_WEBHOOK_URL:
        return
    try:
        import urllib.request
        import json
        payload = json.dumps({
            "text": f"⚠️ YouTube Cookie / Bot-Check Failure on job `{job_id}`!\n"
                    f"**Error**: `{error}`\n"
                    f"💡 Refresh instantly without redeploy:\n"
                    f"`curl -X POST https://<your-app>.onrender.com/admin/cookies -H 'X-Admin-Token: $ADMIN_TOKEN' -H 'Content-Type: application/json' -d '{{\"content\": \"...\"}}'`"
        }).encode("utf-8")
        req = urllib.request.Request(
            ALERT_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[alerting error] Failed to send webhook alert: {e}")
