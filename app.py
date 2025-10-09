import os
import requests
from flask import Flask, request, jsonify

# === Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET = os.getenv("SECRET")

# אם יש לך מזהה מספרי (user id) השאר אותו כמספר/מחרוזת ספרות
# אם יש לך @username אפשר גם לשים "SomeUser" או "@SomeUser"
PRIZE_CONTACT_ID = os.getenv("PRIZE_CONTACT_ID", "8451137138")
PRIZE_CONTACT_LABEL = os.getenv("PRIZE_CONTACT_LABEL", "צור קשר עם נותן הפרס")

if not BOT_TOKEN or ":" not in BOT_TOKEN:
    raise RuntimeError("Missing/invalid BOT_TOKEN")
if not SECRET or len(SECRET) < 8:
    raise RuntimeError("Missing/weak SECRET")
if not PRIZE_CONTACT_ID:
    raise RuntimeError("Missing PRIZE_CONTACT_ID")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

# ---------- helpers ----------
def send_message(chat_id, text, reply_to=None, reply_markup=None, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
        payload["allow_sending_without_reply"] = True
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=15)
        if not r.ok:
            print("send_message fail:", r.status_code, r.text)
    except Exception as e:
        print("send_message error:", e)

def get_admins(chat_id):
    try:
        r = requests.get(f"{API}/getChatAdministrators", params={"chat_id": chat_id}, timeout=10)
        res = r.json().get("result", []) if r.ok else []
        return [m["user"] for m in res if m.get("user") and not m["user"].get("is_bot")]
    except Exception as e:
        print("get_admins error:", e)
        return []

def build_message_link(msg):
    chat = msg.get("chat", {})
    mid = msg.get("message_id")
    if not mid:
        return None
    username = chat.get("username")
    if username:
        return f"https://t.me/{username}/{mid}"
    cid = str(chat.get("id", ""))
    if cid.startswith("-100"):
        return f"https://t.me/c/{cid[4:]}/{mid}"
    return None

def jackpot_button():
    val = str(PRIZE_CONTACT_ID)
    if val.lstrip("@").isalnum() and not val.lstrip("@").isdigit():
        # נראה כמו username
        url = f"https://t.me/{val.lstrip('@')}"
    elif val.isdigit():
        # מזהה מספרי
        url = f"tg://user?id={val}"
    else:
        # ברירת מחדל – עדיין ננסה כ-username
        url = f"https://t.me/{val.lstrip('@')}"
    return {"inline_keyboard": [[{"text": PRIZE_CONTACT_LABEL, "url": url}]]}

# ---------- routes ----------
@app.route("/")
def index():
    return "OK - Slot Winner Bot is alive!"

@app.route(f"/{SECRET}", methods=["POST"])
def webhook():
    # אם רשמת secret_token ב-setWebhook, טלגרם תצרף header תואם.
    hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if hdr is not None and hdr != SECRET:
        return "forbidden", 403

    update = request.get_json(silent=True) or {}
    msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
    if not msg:
        return jsonify(ok=True)

    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type")
    text = (msg.get("text") or "").strip()

    # עזרה קצרה בפרטי
    if chat_type == "private" and text.startswith(("/start", "/help")):
        send_message(chat_id, "🎰 Slot Winner Bot is ready.\nI will notify winners and ping admins on jackpot (777).")
        return jsonify(ok=True)

    # זיהוי מכונת מזל 🎰
    dice = msg.get("dice")
    if dice and dice.get("emoji") == "🎰":
        value = int(dice.get("value", 0))
        if value == 64:  # 64 = 777 Jackpot
            from_user = msg.get("from", {}) or {}
            winner_id = from_user.get("id")
            winner_name = from_user.get("first_name") or from_user.get("username") or "שחקן"
            link = build_message_link(msg)

            # (1) תגובה לזוכה בקבוצה
            reply_text = "🎉 הוצאת 777 וזכית!\nאנא פנה לנותן הפרס בלחיצה על הכפתור."
            send_message(chat_id, reply_text, reply_to=msg.get("message_id"), reply_markup=jackpot_button())

            # (2) הודעה פרטית לכל המנהלים
            admins = get_admins(chat_id)
            if admins:
                info = [
                    "🎰 Jackpot detected (777)!",
                    f"Winner: {winner_name} (id {winner_id})",
                    f"Message: {link}" if link else f"Chat: {chat.get('title') or chat_id}, msg_id: {msg.get('message_id')}",
                ]
                admin_text = "\n".join(info)
                for a in admins:
                    uid = a.get("id")
                    if uid and uid != winner_id:
                        try:
                            send_message(uid, admin_text)
                        except Exception as e:
                            print("notify admin fail:", uid, e)

    return jsonify(ok=True)

# --- local run (Render קורא את PORT מהסביבה) ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
