import os
import requests
from flask import Flask, request, jsonify

# === ENV & Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET = os.getenv("SECRET")  # השתמש במחרוזת ארוכה ואקראית
if not BOT_TOKEN or ":" not in BOT_TOKEN:
    raise RuntimeError("Missing/invalid BOT_TOKEN (set it in Render → Environment).")
if not SECRET or len(SECRET) < 8:
    raise RuntimeError("Missing/weak SECRET (set a long random string in Render → Environment).")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
app = Flask(__name__)

def send_message(chat_id: int, text: str):
    try:
        r = requests.post(
            f"{API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=10
        )
        if not r.ok:
            print("send_message fail:", r.status_code, r.text)
    except Exception as e:
        print("send_message error:", e)

@app.route("/")
def index():
    return "OK - Telegram bot is alive!"

# Webhook (טלגרם ישלח לפה POST)
@app.route(f"/{SECRET}", methods=["POST"])
def webhook():
    # אימות אופציונלי: אם הגדרנו secret_token ב-setWebhook, טלגרם תצרף header תואם
    hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if hdr is not None and hdr != SECRET:
        return "forbidden", 403

    data = request.get_json(silent=True) or {}
    msg = data.get("message") or data.get("edited_message") or data.get("channel_post")

    if msg:
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        text = (msg.get("text") or "").strip()

        # דוגמה: מענה ידידותי בפרטי
        if chat.get("type") == "private" and text.startswith(("/start", "/help")):
            send_message(chat_id,
                "👋 Hi! I'm alive.\nSend any text and I'll echo it back.\n"
                "You can also use /setwebhook to (re)register the webhook."
            )
        else:
            reply = f"קיבלתי: {text}" if text else "קיבלתי הודעה 👍"
            send_message(chat_id, reply)

    return jsonify(ok=True)

# רישום webhook (קריאה חד-פעמית אחרי דפלוי)
@app.route("/setwebhook")
def set_webhook():
    base = request.url_root.replace("http://", "https://")
    if not base.endswith("/"):
        base += "/"
    url = f"{base}{SECRET}"

    # נוסיף secret_token כדי שנוכל לאמת את ה-POST של טלגרם
    params = {
        "url": url,
        "secret_token": SECRET,
        # אופציונלי: צמצום סוגי עדכונים
        # "allowed_updates": ["message", "edited_message", "channel_post"]
    }
    r = requests.get(f"{API}/setWebhook", params=params, timeout=10)
    return r.text, r.status_code, {"Content-Type": "application/json"}

@app.route("/deletewebhook")
def delete_webhook():
    r = requests.get(f"{API}/deleteWebhook", timeout=10)
    return r.text, r.status_code, {"Content-Type": "application/json"}

# דיבאג: בדיקת מצב ה-webhook בטלגרם
@app.route("/getwebhookinfo")
def get_webhook_info():
    r = requests.get(f"{API}/getWebhookInfo", timeout=10)
    return r.text, r.status_code, {"Content-Type": "application/json"}

# להרצה מקומית
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
