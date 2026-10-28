"""Push notifications via ntfy.sh. The click URL opens the dashboard at the alert's row."""
import os, urllib.request

def push(message, title="Card radar", click=None, topic=None):
    topic = topic or os.environ.get("NTFY_TOPIC")
    if not topic:
        raise RuntimeError("NTFY_TOPIC not set in .env")
    headers = {"Title": title}
    if click:
        headers["Click"] = click
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=message.encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()
