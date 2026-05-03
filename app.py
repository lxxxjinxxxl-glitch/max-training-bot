import re
import time
import asyncio
import os
import requests
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
last_surnames = MY_SURNAMES  # храним последний текст
edit_waiting = {}  # {user_id: True} — ждём новый текст

app = FastAPI(root_path="/hockey")

@app.get("/")
@app.get("/hockey")
def health():
    return {"status": "ok"}

def send_message(chat_id, text):
    if int(chat_id) < 0:
        url = f"{API_URL}?chat_id={chat_id}"
    else:
        url = f"{API_URL}?user_id={chat_id}"
    resp = requests.post(url, headers={"Authorization": BOT_TOKEN, "Content-Type": "application/json"}, json={"text": text})
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

def send_to_user(user_id, text):
    resp = requests.post(f"{API_URL}?user_id={user_id}", headers={"Authorization": BOT_TOKEN, "Content-Type": "application/json"}, json={"text": text})
    print(f"SEND: {resp.status_code}")
    return resp.status_code

def is_training(text):
    triggers = ["Внимание", "▶️", "Место проведения", "Лед:", "ОФП:", "Направленность"]
    hits = sum(1 for t in triggers if t.lower() in text.lower())
    has_date = bool(re.search(r'\d{2}\.\d{2}\.\d{2,4}', text))
    return hits >= 3 and has_date

@app.post("/webhook")
async def webhook(req: Request):
    global last_training_time, last_message_id, last_chat_id, last_surnames, edit_waiting

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

    # === ЛИЧКА ===
    if is_private and text:

        # Ждём новый текст после /edit
        if user_id in edit_waiting:
            del edit_waiting[user_id]
            new_text = text.strip()

            if new_text == "-":
                # Удалить запись
                delete_message(last_message_id)
                send_to_user(user_id, "✅ Запись удалена")
                last_message_id = None
                last_training_time = 0
                last_surnames = MY_SURNAMES
                return {"ok": True}

            # Редактировать
            edit_message(last_message_id, new_text)
            last_surnames = new_text
            send_to_user(user_id, f"✅ Запись изменена:\n{new_text}")
            return {"ok": True}

        # /start
        if text == "/start":
            send_to_user(user_id,
                "Привет! 🏒\n"
                "/edit — изменить последнюю запись\n"
                "/delete — удалить запись\n"
                "/status — статус\n"
                "/chatid — ID чата"
            )
            return {"ok": True}

        # /edit — показать текущий текст и ждать новый
        if text == "/edit":
            if last_message_id:
                send_to_user(user_id,
                    f"📝 Текущая запись:\n{last_surnames}\n\n"
                    "Введите новый текст (одну или две фамилии через перенос строки).\n"
                    "Или введите «-» (прочерк) чтобы удалить запись."
                )
                edit_waiting[user_id] = True
            else:
                send_to_user(user_id, "❌ Нет активной записи")
            return {"ok": True}

        # /delete — удалить запись
        if text == "/delete":
            if last_message_id:
                delete_message(last_message_id)
                send_to_user(user_id, "✅ Запись удалена")
                last_message_id = None
                last_training_time = 0
                last_surnames = MY_SURNAMES
            else:
                send_to_user(user_id, "❌ Нечего удалять")
            return {"ok": True}

        # /status
        if text == "/status":
            if last_message_id:
                send_to_user(user_id,
                    f"✅ Запись активна\n"
                    f"Чат: {last_chat_id}\n"
                    f"Текст: {last_surnames}\n"
                    f"msg_id: {last_message_id}"
                )
            else:
                send_to_user(user_id, "❌ Нет активной записи")
            return {"ok": True}

        # /chatid
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

            last_surnames = MY_SURNAMES

            resp = send_message(chat_id, MY_SURNAMES)
            if isinstance(resp, dict) and resp.get("message"):
                last_message_id = resp["message"]["body"]["mid"]
                last_chat_id = chat_id
                last_training_time = now
                print(f"✅ Записан! msg_id={last_message_id}")

                send_to_user(user_id, f"📝 Запись:\n{last_surnames}")

    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)