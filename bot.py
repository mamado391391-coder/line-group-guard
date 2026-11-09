import base64
import hashlib
import hmac
import os

import requests
from flask import Flask, abort, request

app = Flask(__name__)

CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_API = "https://api.line.me/v2/bot"

# In-memory settings for a simple test. These reset when the service restarts.
lurk_by_group = {}


def valid_signature(body: bytes, signature: str) -> bool:
    if not CHANNEL_SECRET or not signature:
        return False
    digest = hmac.new(
        CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def reply(reply_token: str, message: str) -> None:
    if not CHANNEL_ACCESS_TOKEN or not reply_token:
        return
    response = requests.post(
        f"{LINE_API}/message/reply",
        headers={
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": message}],
        },
        timeout=10,
    )
    response.raise_for_status()


@app.get("/")
def health():
    return "LINE Group Guard is running", 200


@app.post("/webhook")
def webhook():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
    if not valid_signature(body, signature):
        abort(400)

    payload = request.get_json(silent=True) or {}
    for event in payload.get("events", []):
        event_type = event.get("type")
        source = event.get("source", {})
        group_id = source.get("groupId")
        reply_token = event.get("replyToken", "")

        if event_type == "memberJoined" and group_id:
            if lurk_by_group.get(group_id, True):
                joined = event.get("joined", {}).get("members", [])
                count = len(joined) or 1
                reply(
                    reply_token,
                    f"تنبيه حماية: انضم {count} عضو جديد للجروب. "
                    "تم تسجيل حدث الانضمام. "
                    "الطرد التلقائي غير متاح عبر LINE Messaging API الرسمية."
                )

        elif event_type == "message" and group_id:
            message = event.get("message", {})
            if message.get("type") != "text":
                continue

            command = message.get("text", "").strip().lower()

            if command in (".help", ".مساعدة"):
                reply(
                    reply_token,
                    "أوامر Group Guard:\n"
                    ".help — المساعدة\n"
                    ".lurk on — تشغيل تنبيهات دخول الأعضاء\n"
                    ".lurk off — إيقاف تنبيهات دخول الأعضاء\n\n"
                    "ملاحظة: هذا الإصدار ينبه ويسجل الحدث فقط؛ "
                    "لا يستطيع طرد الأعضاء أو إدارة صلاحيات الجروب."
                )
            elif command == ".lurk on":
                lurk_by_group[group_id] = True
                reply(reply_token, "تم تشغيل تنبيهات دخول الأعضاء.")
            elif command == ".lurk off":
                lurk_by_group[group_id] = False
                reply(reply_token, "تم إيقاف تنبيهات دخول الأعضاء.")

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))