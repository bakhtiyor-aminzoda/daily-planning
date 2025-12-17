from fastapi import FastAPI, Request, Header, HTTPException
import requests
import re

app = FastAPI()

BOT_TOKEN = "8362883058:AAFEKdE-4DICxZ3-gKLpZOmPp9csmUe9tQk"
API_KEY = "super-secret-key"

# 🧠 ВРЕМЕННОЕ ХРАНИЛИЩЕ (потом БД)
users = {}  # email -> telegram_id

def send_telegram(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text
    })

# -------------------------
# TELEGRAM WEBHOOK
# -------------------------
@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text == "/start":
        send_telegram(
            chat_id,
            "Привет 👋\n\nВведи свою корпоративную почту, чтобы получать план дня 📅"
        )
        return {"ok": True}

    # если ввели email
    if re.match(r"[^@]+@[^@]+\.[^@]+", text):
        email = text.lower()
        users[email] = chat_id

        send_telegram(
            chat_id,
            f"✅ Почта *{email}* сохранена.\n\n"
            "Теперь я буду присылать тебе план дня каждый день в 09:00 📅",
        )
        return {"ok": True}

    send_telegram(
        chat_id,
        "❌ Пожалуйста, введи корректную корпоративную почту"
    )

    return {"ok": True}

# -------------------------
# POWER AUTOMATE WEBHOOK
# -------------------------
@app.post("/api/webhook/outlook")
async def outlook_webhook(
    request: Request,
    x_api_key: str = Header(None)
):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()

    email = data.get("email", "").lower()
    events = data.get("events", [])

    chat_id = users.get(email)
    if not chat_id:
        return {"status": "user not registered"}

    if not events:
        message = "📅 Сегодня встреч нет 🎉"
    else:
        message = "📅 План на сегодня:\n\n"
        for e in events:
            message += f"{e['start']}–{e['end']} • {e['subject']}\n"

    send_telegram(chat_id, message)
    return {"status": "ok"}
