import re
import time
import asyncio
import os
import requests
import json
from fastapi import FastAPI, Request

BOT_TOKEN = os.getenv("BOT_TOKEN", "f9LHodD0cOIzxFR48PGWufr_4B9omZdcIZnBaHe9izzs8f5lvtYDS-_4QeNWF9T8YXXj2Q2L9fcPMHC6JDNW")
API_URL = "https://platform-api.max.ru/messages"
MY_SURNAMES = "Щекетов\nОкуньков"
DELAY = 1
COOLDOWN = 1800
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", None)
OWNER_USER_ID = "125743856"

last_training_time = 0
last_message_id = None
last_chat_id = None
edit_state = {}

app = FastAPI(root_path="/hockey")

@app.get("/")
@app.get("/hockey")
def health():
    return {"status": "ok"}

def send_message(chat_id, text, reply_keyboard=None):
    if int(chat_id) < 0:
        url = f"{API_URL}?chat_id={chat_id}"
    else:
        url = f"{API_URL}?user_id={chat_id}"
    payload = {"text": text}
    if reply_keyboard:
        payload["keyboard"] = reply_keyboard
    resp = requests.post(url, headers={"Authorization": BOT_TOKEN, "Content-Type": "application/json"}, json=payload)
    print(f"SEND: {resp.status_code}")
    try: return resp.json()
    except: return {"ok": False}

def edit_message(message_id, text):
    resp = requests.put(f"https://platform-api.max.ru/messages?message_id={message_id}", headers={"Authorization": BOT_TOKEN, "Content-Type": "application/json"}, json={"text": text})
    print(f"EDIT: {resp.status_code}")
    return resp.status_code

def delete_message(message_id):
    resp = requests.delete(f"https://platform-api.max.ru/messages?message_id={message_id}", headers={"Authorization": BOT_TOKEN})
    print(f"DELETE: {resp.status_code}")
    return resp.status_code

def send_to_user(user_id, text, reply_keyboard=None):
    return send_message(user_id, text, reply_keyboard)

def is_training(text):
    triggers = ["Внимание", "▶️", "Место проведения", "Лед:", "ОФП:", "Направленность"]
    hits = sum(1 for t in triggers if t.lower() in text.lower())
    has_date = bool(re.search(r'\d{2}\.\d{2}\.\d{2,4}', text))
    return hits >= 3 and has_date

def control_keyboard():
    """Клавиатура с кнопками управления (как у старого бота)"""
    return json.dumps({
        "keyboard": [
            [{"text": "✏️ Редактировать запись"}],
            [{"text": "🗑 Удалить запись"}],
            [{"text": "📊 Статус"}]
        ],
        "resize_keyboard": True
    })

@app.post("/webhook")
async def webhook(req: Request):
    global last_training_time, last_message_id, last_chat_id, edit_state

    data = await req.json()
    utype = data.get("update_type", "")

    if utype == "message_callback" or data.get("callback"):
        return {"ok": True}

    if utype != "message_created":
        return {"ok": True}

    msg = data.get("message", {})
    text = msg.get("body", {}).get("text", "").strip()
    chat = msg.get("recipient", {})
    chat_id = str(chat.get("chat_id") or chat.get("user_id") or "")
    user_id = str(msg.get("sender", {}).get("user_id", ""))
    is_private = chat_id.isdigit() and int(chat_id) > 0

    print(f"💬 chat_id={chat_id} | user={user_id} | private={is_private} | text={text[:80]}")

    # === FSM РЕДАКТИРОВАНИЯ (в личке) ===
    if is_private and user_id in edit_state:
        target_id = edit_state.pop(user_id)
        new_text = text.strip()
        if new_text:
            edit_message(target_id, new_text)
            send_to_user(user_id, f"✅ Изменено на:\n{new_text}", control_keyboard())
        else:
            send_to_user(user_id, "❌ Текст не может быть пустым", control_keyboard())
        return {"ok": True}

    # === ЛИЧКА: КОМАНДЫ И КНОПКИ ===
    if is_private and text:
        if text == "/start" or text == "🏒 Главное меню":
            send_to_user(user_id, "Управление записью:", control_keyboard())
            return {"ok": True}

        if text == "✏️ Редактировать запись":
            if last_message_id:
                edit_state[user_id] = last_message_id
                send_to_user(user_id, "✏️ Введите новый текст (например: Щекетов\nОкуньков):")
            else:
                send_to_user(user_id, "❌ Нет активной записи", control_keyboard())
            return {"ok": True}

        if text == "🗑 Удалить запись":
            if last_message_id:
                delete_message(last_message_id)
                send_to_user(user_id, "✅ Запись удалена", control_keyboard())
                last_message_id = None
                last_training_time = 0
            else:
                send_to_user(user_id, "❌ Нечего удалять", control_keyboard())
            return {"ok": True}

        if text == "📊 Статус":
            if last_message_id:
                send_to_user(user_id, f"✅ Запись активна\nЧат: {last_chat_id}\nmsg_id: {last_message_id}", control_keyboard())
            else:
                send_to_user(user_id, "❌ Нет активной записи", control_keyboard())
            return {"ok": True}

        if text.startswith("/chatid"):
            send_to_user(user_id, f"chat_id: {chat_id}")
            return {"ok": True}

    # === ГРУППОВОЙ ЧАТ: ТРЕНИРОВКА ===
    if not is_private and text:
        if TARGET_CHAT_ID and chat_id != TARGET_CHAT_ID:
            return {"ok": True}

        if is_training(text):
            now = time.time()
            if now - last_training_time < COOLDOWN:
                print("🔁 Кулдаун")
                return {"ok": True}

            print(f"🎯 Тренировка! Жду {DELAY} сек...")
            await asyncio.sleep(DELAY)

            resp = send_message(chat_id, MY_SURNAMES)
            if isinstance(resp, dict) and resp.get("message"):
                last_message_id = resp["message"]["body"]["mid"]
                last_chat_id = chat_id
                last_training_time = now
                print(f"✅ Записан! msg_id={last_message_id}")

                # Уведомление в личку с клавиатурой
                send_to_user(
                    OWNER_USER_ID,
                    f"📝 Запись в чате:\n{MY_SURNAMES}",
                    control_keyboard()
                )

    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)