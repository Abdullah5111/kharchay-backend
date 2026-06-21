import json
import urllib.request
from celery import shared_task

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

@shared_task
def send_push(tokens, title, body, data):
    if not tokens:
        return
    messages = [{"to": t, "title": title, "body": body, "data": data} for t in tokens]
    try:
        req = urllib.request.Request(
            EXPO_PUSH_URL,
            data=json.dumps(messages).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass  # best-effort; never break the caller
