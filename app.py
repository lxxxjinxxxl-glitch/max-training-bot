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

def send_message(chat_id, text, inline_keyboard=None):
    if int(chat_id) < 0:
        url = f"{API_URL}?chat_id={chat_id}"
    else:
        url = f"{API_URL}?user_id={chat_id}"
    payload = {"text": text}
    if inline_keyboard:
        payload["attachments"] = inline_keyboard["attachments"]
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

def send_to_user(user_id, text, inline_keyboard=None):
    return send_message(user_id, text, inline_keyboard)

def is_training(text):
    triggers = ["Внимание", "▶️", "Место проведения", "Лед:", "ОФП:", "Направленность"]
    hits = sum(1 for t in triggers if t.lower() in text.lower())
    has_date = bool(re.search(r'\d{2}\.\d{2}\.\d{2,4}', text))
    return hits >= 3 and has_date

def control_buttons(msg_id):
    return {
        "attachments": [{
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {"type": "callback", "text": "✏️ Редактировать", "payload": f"edit_{msg_id}"},
                        {"type": "callback", "text": "🗑 Удалить", "payload": f"delete_{msg_id}"}
                    ]
                ]
            }
        }]
    }

@app.post("/webhook")
async def webhook(req: Request):
    global last_training_time, last_message_id, last_chat_id, edit_state

    data = await req.json()
    utype = data.get("update_type", "")

    # === CALLBACK (кнопки) ===
    if utype == "message_callback" or data.get("callback"):
        cb = data.get("callback") or data
        user_id = str(cb.get("user", {}).get("user_id") or cb.get("from", {}).get("user_id") or "")
        cb_data = cb.get("payload") or cb.get("data") or ""

        if cb_data.startswith("delete_"):
            target_id = cb_data.split("_")[1]
            delete_message(target_id)
            if last_message_id == target_id:
                last_message_id = None
                last_training_time = 0
            send_to_user(user_id, "✅ Сообщение удалено")
            return {"ok": True}

        if cb_data.startswith("edit_"):
            target_id = cb_data.split("_")[1]
            edit_state[user_id] = target_id
            send_to_user(user_id, "✏️ Введите новый текст (например: Щекетов):")
            return {"ok": True}

        return {"ok": True}

    # === НОВЫЕ СООБЩЕНИЯ ===
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
            send_to_user(user_id, f"✅ Изменено на:\n{new_text}")
        else:
            send_to_user(user_id, "❌ Текст не может быть пустым")
        return {"ok": True}

    # === ЛИЧКА: КОМАНДЫ ===
    if is_private and text:
        if text == "/start":
            send_to_user(user_id, "Привет! 🏒\n/статус — статус записи\n/отмена — удалить запись\n/chatid — ID чата")
            return {"ok": True}
        if text.startswith("/chatid"):
            send_to_user(user_id, f"chat_id: {chat_id}")
            return {"ok": True}
        if text == "/статус":
            if last_message_id:
                send_to_user(user_id, f"✅ Запись активна\nЧат: {last_chat_id}\nmsg_id: {last_message_id}")
            else:
                send_to_user(user_id, "❌ Нет активной записи")
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

                # Уведомление в личку с кнопками
                send_to_user(
                    OWNER_USER_ID,
                    f"📝 Запись в чате {chat_id}:\n{MY_SURNAMES}",
                    control_buttons(last_message_id)
                )

    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)