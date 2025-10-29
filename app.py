import os
import requests
from flask import Flask, request, jsonify

# === Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET = os.getenv("SECRET")

# בעל הבוט (User ID שלך). חובה.
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# רשימת הקבוצות המותרות (comma-separated), למשל: "-1001234567890,-100987654321"
ALLOWED_CHAT_IDS_RAW = os.getenv("ALLOWED_CHAT_IDS", "").strip()

# אם יש לך מזהה מספרי של נותן הפרס – השאר ספרות; אם זה username השתמש ב-@Name או Name
PRIZE_CONTACT_ID = os.getenv("PRIZE_CONTACT_ID", "8451137138")
PRIZE_CONTACT_LABEL = os.getenv("PRIZE_CONTACT_LABEL", "צור קשר עם נותן הפרס")

if not BOT_TOKEN or ":" not in BOT_TOKEN:
    raise RuntimeError("Missing/invalid BOT_TOKEN")
if not SECRET or len(SECRET) < 8:
    raise RuntimeError("Missing/weak SECRET")
if OWNER_ID <= 0:
    raise RuntimeError("Missing/invalid OWNER_ID")

def _parse_chat_ids(raw: str):
    s = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            s.add(int(part))
        except ValueError:
            pass
    return s

ALLOWED_CHATS = _parse_chat_ids(ALLOWED_CHAT_IDS_RAW)

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
        if r.ok:
            return r.json().get("result")  # נחזיר את אובייקט ההודעה (כולל message_id)
        else:
            print("send_message fail:", r.status_code, r.text)
    except Exception as e:
        print("send_message error:", e)
    return None

def pin_message(chat_id, message_id, silent=True):
    """ניסיון לנעוץ הודעה. דורש שהבוט יהיה אדמין עם can_pin_messages."""
    try:
        r = requests.post(
            f"{API}/pinChatMessage",
            json={"chat_id": chat_id, "message_id": message_id, "disable_notification": silent},
            timeout=10
        )
        if not r.ok:
            print("pin_message fail:", r.status_code, r.text)
    except Exception as e:
        print("pin_message error:", e)

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
        url = f"https://t.me/{val.lstrip('@')}"
    return {"inline_keyboard": [[{"text": PRIZE_CONTACT_LABEL, "url": url}]]}

def is_owner(uid):
    return uid and int(uid) == OWNER_ID

def is_allowed_chat(cid):
    return cid in ALLOWED_CHATS

# ---------- routes ----------
@app.route("/")
def index():
    return "OK - Slot Winner Bot is alive!"

@app.route(f"/{SECRET}", methods=["POST"])
def webhook():
    # אם קבעת secret_token ב-setWebhook, טלגרם תשלח את ההדר הזה:
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
    from_user = msg.get("from") or {}
    user_id = from_user.get("id")
    text = (msg.get("text") or "").strip()

    # --- חסימה ברמת צ'אטים ---
    if chat_type in {"group", "supergroup", "channel"}:
        if not is_allowed_chat(chat_id):
            # מתעלמים לחלוטין אם זו לא קבוצה מורשית
            return jsonify(ok=True)

    # --- חסימה בפרטי: רק הבעלים ---
    if chat_type == "private":
        if not is_owner(user_id):
            # אפשר גם לשלוח הודעה "Private bot" אם תרצה
            return jsonify(ok=True)
        # פקודות עזרה וזיהוי
        if text == "/start":
            send_message(chat_id, "שלח את האימוג׳י 🎰 ואולי תזכה! \nSend the 🎰 emoji and maybe you’ll win big!")
            return jsonify(ok=True)
        if text == "/help":
            send_message(chat_id, "🎰 Private Slot Winner Bot.\nThis bot is restricted to the owner and approved groups only.")
            return jsonify(ok=True)
        if text == "/id":
            send_message(chat_id, f"your_id: {user_id}\nchat_id: {chat_id}\nallowed_chats: {', '.join(map(str, ALLOWED_CHATS)) or '(none)'}")
            return jsonify(ok=True)

    # --- לוגיקת הזכייה בקבוצות מורשות ---
    dice = msg.get("dice")
    if dice and dice.get("emoji") == "🎰":
        value = int(dice.get("value", 0))
        if value != 64:  # 64 = 777 Jackpot
            winner_name = from_user.get("first_name") or from_user.get("username") or "שחקן"
            link = build_message_link(msg)

            # (1) תגובה לזוכה בקבוצה
            winner_id = from_user.get("id")
            winner_username = from_user.get("username")
            first_name = from_user.get("first_name", "שחקן")

            if winner_username:
                mention = f"@{winner_username}"
            else:
                # תיוג אמיתי גם למי שאין לו username
                mention = f'<a href="tg://user?id={winner_id}">{first_name}</a>'

            reply_text = (
                f"כל הכבוד {mention}! Congratulations \n"
                f"You got 7️⃣ 7️⃣ 7️⃣ and won the prize"
                f"הוצאת 7️⃣ 7️⃣ 7️⃣ וזכית!\n\n"
                f"אנא לחץ על הכפתור 👇 כדי לקבל את המתנה 🎁"
                f"Please click the button 👇 to claim your reward 🎁"
            )

            sent = send_message(
                chat_id,
                reply_text,
                reply_to=msg.get("message_id"),
                reply_markup=jackpot_button(),
                parse_mode="HTML"
            )

            # ננסה לנעוץ את הודעת הזכייה
            if sent and isinstance(sent, dict):
                mid = sent.get("message_id")
                if mid:
                    pin_message(chat_id, mid, silent=True)

            # (2) הודעה פרטית למנהלים (Best effort)
            admins = get_admins(chat_id)
            if admins:
                info = [
                    "🎰 Jackpot detected (777)!",
                    f"Winner: {winner_name} (id {from_user.get('id')})",
                    f"Message: {link}" if link else f"Chat: {chat.get('title') or chat_id}, msg_id: {msg.get('message_id')}",
                ]
                admin_text = "\n".join(info)
                for a in admins:
                    uid = a.get("id")
                    if uid and uid != from_user.get("id"):
                        try:
                            send_message(uid, admin_text)
                        except Exception as e:
                            print("notify admin fail:", uid, e)

    return jsonify(ok=True)

# --- local run ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
