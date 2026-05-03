import re
import time
import os
import requests
from fastapi import FastAPI, Request

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "f9LHodD0cOIzxFR48PGWufr_4B9omZdcIZnBaHe9izzs8f5lvtYDS-_4QeNWF9T8YXXj2Q2L9fcPMHC6JDNW")
API_URL = "https://platform-api.max.ru/messages"

MY_SURNAMES = "Щекетов\nОкуньков"
DELAY = 1
COOLDOWN = 1800

TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", None)

# ========== ПАМЯТЬ ==========
last_training_time = 0
last_message_id = None
last_chat_id = None

app = FastAPI(root_path="/hockey")

# ========== ФУНКЦИИ API ==========

def send_message(chat_id, text):
    resp = requests.post(
        f"{API_URL}?chat_id={chat_id}",
        headers={"Authorization": BOT_TOKEN, "Content-Type": "application/json"},
        json={"text": text}
    )
    print(f"SEND to {chat_id}: {resp.status_code}")
    try:
        return resp.json()
    except:
        return {"ok": False}

def edit_message(message_id, text):
    resp = requests.put(
        f"https://platform-api.max.ru/messages?message_id={message_id}",
        headers={"Authorization": BOT_TOKEN, "Content-Type": "application/json"},
        json={"text": text}
    )
    print(f"EDIT {message_id}: {resp.status_code}")
    return resp.status_code

def delete_message(message_id):
    resp = requests.delete(
        f"https://platform-api.max.ru/messages?message_id={message_id}",
        headers={"Authorization": BOT_TOKEN}
    )
    print(f"DELETE {message_id}: {resp.status_code}")
    return resp.status_code

def send_to_user(user_id, text):
    resp = requests.post(
        f"{API_URL}?user_id={user_id}",
        headers={"Authorization": BOT_TOKEN, "Content-Type": "application/json"},
        json={"text": text}
    )
    print(f"SEND to user {user_id}: {resp.status_code}")
    return resp.status_code

# ========== ЛОГИКА ==========

def is_training(text):
    triggers = ["Внимание", "▶️", "Место проведения", "Лед:", "ОФП:", "Направленность"]
    hits = sum(1 for t in triggers if t.lower() in text.lower())
    has_date = bool(re.search(r'\d{2}\.\d{2}\.\d{2,4}', text))
    return hits >= 3 and has_date

# ========== WEBHOOK ==========

@app.post("/webhook")
async def webhook(req: Request):
    global last_training_time, last_message_id, last_chat_id

    data = await req.json()
    utype = data.get("update_type", "")

    if utype == "message_callback":
        return {"ok": True}

    if utype != "message_created":
        return {"ok": True}

    msg = data.get("message", {})
    text = msg.get("body", {}).get("text", "").strip()
    chat = msg.get("recipient", {})
    chat_id = str(chat.get("chat_id") or chat.get("user_id") or "")
    user_id = msg.get("sender", {}).get("user_id", "")
    msg_id = msg.get("body", {}).get("mid", "")
    is_private = chat_id.isdigit() and int(chat_id) > 0

    print(f"💬 chat_id={chat_id} | user={user_id} | private={is_private} | text={text[:80]}")

    if is_private and text:

        if text.startswith("/chatid"):
            send_to_user(user_id, f"chat_id этого чата: {chat_id}")
            return {"ok": True}

        if text.startswith("/отмена"):
            if last_message_id and last_chat_id:
                delete_message(last_message_id)
                send_to_user(user_id, "✅ Запись удалена")
                last_message_id = None
                last_training_time = 0
            else:
                send_to_user(user_id, "❌ Нечего отменять")
            return {"ok": True}

        if text.startswith("/отредактировать"):
            new_text = text.replace("/отредактировать", "").strip()
            if last_message_id and last_chat_id:
                edit_message(last_message_id, new_text)
                send_to_user(user_id, f"✅ Изменено на:\n{new_text}")
            else:
                send_to_user(user_id, "❌ Нечего редактировать")
            return {"ok": True}

        if text == "/статус":
            if last_message_id:
                send_to_user(user_id, f"✅ Записан в {last_chat_id}\nmsg_id: {last_message_id}")
            else:
                send_to_user(user_id, "❌ Нет активной записи")
            return {"ok": True}

    if not is_private and text:

        if TARGET_CHAT_ID and chat_id != TARGET_CHAT_ID:
            return {"ok": True}

        if is_training(text):
            now = time.time()
            if now - last_training_time < COOLDOWN:
                print("🔁 Кулдаун, пропускаем")
                return {"ok": True}

            print(f"🎯 Тренировка в {chat_id}! Жду {DELAY} сек...")
            time.sleep(DELAY)

            resp = send_message(chat_id, MY_SURNAMES)
            if isinstance(resp, dict) and resp.get("message"):
                last_message_id = resp["message"]["body"]["mid"]
                last_chat_id = chat_id
                last_training_time = now
                print(f"✅ Записан! msg_id={last_message_id}")

    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)