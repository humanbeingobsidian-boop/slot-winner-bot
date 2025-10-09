import os
import requests
from flask import Flask, request, jsonify

# === Config from env ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET = os.getenv("SECRET")
PRIZE_CONTACT_ID = 8451137138 
PRIZE_CONTACT_LABEL = ("צור קשר עם נותן הפרס")

if not BOT_TOKEN or ":" not in BOT_TOKEN:
    raise RuntimeError("Missing/invalid BOT_TOKEN")
if not SECRET or len(SECRET) < 8:
    raise RuntimeError("Missing/weak SECRET")
if not PRIZE_CONTACT_ID:
    raise RuntimeError("Missing PRIZE_CONTACT_ID")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

# -------- helpers --------
def send_message(chat_id: int, text: str, reply_to: int | None = None, reply_markup: dict | None = None, parse_mode: str | None = None):
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

def get_admins(chat_id: int):
    """Return list of user dicts for chat admins (non-bot)."""
    try:
        r = requests.get(f"{API}/getChatAdministrators", params={"chat_id": chat_id}, timeout=10)
        res = r.json().get("result", []) if r.ok else []
        admins = []
        for m in res:
            u = m.get("user") or {}
            if u.get("is_bot"):
                continue
            admins.append(u)
        return admins
    except Exception as e:
        print("get_admins error:", e)
        return []

def build_message_link(msg: dict) -> str | None:
    """
    Try to build a clickable link to the original message.
    For public supergroups/channels with username: https://t.me/<username>/<message_id>
    For private supergroups: https://t.me/c/<internal_id>/<message_id> where internal_id = abs(chat_id) without -100 prefix.
    """
    chat = msg.get("chat", {})
    mid = msg.get("message_id")
    if not mid:
        return None
    username = chat.get("username")
    if username:
        return f"https://t.me/{username}/{mid}"
    # supergroups/channels have id like -100123456789
    cid = str(chat.get("id", ""))
    if cid.startswith("-100"):
        internal = cid[4:]  # drop -100
        return f"https://t.me/c/{internal}/{mid}"
    return None

def jackpot_reply_markup() -> dict:
    url = f"https://t.me/{PRIZE_CONTACT_ID}"
    return {"inline_keyboard": [[{"text": PRIZE_CONTACT_LABEL, "url": url}]]}

# -------- Flask routes --------
@app.route("/")
def index():
    return "OK - Slot Winner Bot is alive!"

@app.route(f"/{SECRET}", methods=["POST"])
def webhook():
    # optional header check if you also set secret_token in /setwebhook
    hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if hdr is not None and hdr != SECRET:
        return "forbidden", 403

    update = request.get_json(silent=True) or {}
    msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
    if not msg:
        return jsonify(ok=True)

    # Handle /start in private for convenience
    chat = msg.get("chat", {})
    chat_type = chat.get("type")
    text = (msg.get("text") or "").strip()
    if chat_type == "private" and text.startswith(("/start", "/help")):
        send_message(
            chat["id"],
            "🎰 Slot Winner Bot is ready.\nI will notify winners and ping admins on jackpot (777)."
        )
        return jsonify(ok=True)

    # ---- Detect slot machine jackpot ----
    dice = msg.get("dice")
    if dice and dice.get("emoji") == "🎰":
        value = int(dice.get("value", 0))
        # Jackpot is value == 64 for 🎰 per Telegram docs
        if value != 64:
            from_user = msg.get("from", {}) or {}
            winner_id = from_user.get("id")
            winner_name = from_user.get("first_name") or from_user.get("username") or "שחקן"
            link = build_message_link(msg)

            # 1) Reply to the winner in the group
            lines = [
                "הוצאת 777 וזכית!🎉",
                f"אנא פנה ל: @{PRIZE_CONTACT_ID}",
            ]
            reply_text = "\n".join(lines)
            send_message(chat["id"], reply_text, reply_to=msg.get("message_id"), reply_markup=jackpot_reply_markup())

            # 2) Notify all admins in private (best effort)
            admins = get_admins(chat["id"])
            if admins:
                info_lines = [
                    "🎰 Jackpot detected (777)!",
                    f"Winner: {winner_name} (id {winner_id})",
                ]
                if link:
                    info_lines.append(f"Message: {link}")
                else:
                    info_lines.append(f"Chat: {chat.get('title') or chat.get('id')}, msg_id: {msg.get('message_id')}")
                admin_text = "\n".join(info_lines)

                for a in admins:
                    uid = a.get("id")
                    if not uid or uid == winner_id:
                        continue
                    try:
                        send_message(uid, admin_text)
                    except Exception as e:
                        # Most common: Forbidden 403 (user hasn't started the bot)
                        print("notify admin fail:", uid, e)

    return jsonify(ok=True)

@app.route("/setwebhook")
def set_webhook():
    base = request.url_root.replace("http://", "https://")
    if not base.endswith("/"):
        base += "/"
    url = f"{base}{SECRET}"
    params = {"url": url, "secret_token": SECRET}
    r = requests.get(f"{API}/setWebhook", params=params, timeout=10)
    return r.text, r.status_code, {"Content-Type": "application/json"}

@app.route("/deletewebhook")
def delete_webhook():
    r = requests.get(f"{API}/deleteWebhook", timeout=10)
    return r.text, r.status_code, {"Content-Type": "application/json"}

@app.route("/getwebhookinfo")
def get_webhook_info():
    r = requests.get(f"{API}/getWebhookInfo", timeout=10)
    return r.text, r.status_code, {"Content-Type": "application/json"}

# local run
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
