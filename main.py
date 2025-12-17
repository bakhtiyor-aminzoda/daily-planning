from fastapi import FastAPI, Request, Header, HTTPException
import requests
import re
import os

from dotenv import load_dotenv

# =========================
# LOAD ENV
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not API_KEY:
    raise RuntimeError("API_KEY is not set")

app = FastAPI()

# =========================
# TEMP STORAGE (MVP)
# =========================
# email -> telegram_id
users: dict[str, int] = {}

# email -> last sent plan text
last_plans: dict[str, str] = {}

# =========================
# TELEGRAM UI
# =========================
def main_menu_keyboard():
    return {
        "keyboard": [
            ["📅 План на сегодня", "📆 План на завтра"],
            ["🔁 Повторить последний план"],
            ["⚙️ Настройки", "ℹ️ Помощь"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

# =========================
# TELEGRAM SENDER
# =========================
def send_telegram(chat_id: int, text: str, keyboard: dict | None = None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    if keyboard:
        payload["reply_markup"] = keyboard

    requests.post(url, json=payload, timeout=10)

# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {"status": "ok"}

# =========================
# TELEGRAM WEBHOOK
# =========================
@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    # /start
    if text == "/start":
        send_telegram(
            chat_id,
            "Привет 👋\n\n"
            "Я помогу тебе получать план дня из Outlook 📅\n\n"
            "Сначала введи *корпоративную почту* 👇",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    # Email input
    if re.match(r"[^@]+@[^@]+\.[^@]+", text):
        email = text.lower()
        users[email] = chat_id

        send_telegram(
            chat_id,
            f"✅ Почта *{email}* сохранена.\n\n"
            "Теперь я буду присылать тебе план дня *каждый день в 09:00* 📅",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    # =========================
    # BUTTON HANDLERS
    # =========================

    if text == "📅 План на сегодня":
        send_telegram(
            chat_id,
            "📅 План на сегодня будет автоматически прислан утром.\n\n"
            "Если хочешь получить его *прямо сейчас*, нажми 🔁 *Повторить последний план*.",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    if text == "📆 План на завтра":
        send_telegram(
            chat_id,
            "📆 *План на завтра*\n\n"
            "⏳ Функция в разработке.\n"
            "Совсем скоро ты сможешь смотреть завтрашний день заранее 😉",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    if text == "🔁 Повторить последний план":
        # ищем email по chat_id
        email = next((e for e, cid in users.items() if cid == chat_id), None)

        if not email or email not in last_plans:
            send_telegram(
                chat_id,
                "🔁 Пока нет сохранённого плана.\n\n"
                "Он появится после первой автоматической рассылки 📅",
                keyboard=main_menu_keyboard()
            )
            return {"ok": True}

        send_telegram(
            chat_id,
            f"🔁 *Последний план:*\n\n{last_plans[email]}",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    if text == "⚙️ Настройки":
        send_telegram(
            chat_id,
            "⚙️ *Настройки*\n\n"
            "Скоро здесь появится:\n"
            "• время рассылки\n"
            "• таймзона\n"
            "• рабочие дни\n\n"
            "Stay tuned 😉",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    if text == "ℹ️ Помощь":
        send_telegram(
            chat_id,
            "ℹ️ *Как пользоваться ботом:*\n\n"
            "1️⃣ Введи корпоративную почту\n"
            "2️⃣ Получай план дня автоматически\n"
            "3️⃣ Используй кнопки для управления\n\n"
            "Если что-то пошло не так — напиши /start",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    # Fallback
    send_telegram(
        chat_id,
        "🤔 Я тебя не понял.\n\n"
        "Используй кнопки ниже 👇",
        keyboard=main_menu_keyboard()
    )

    return {"ok": True}

# =========================
# POWER AUTOMATE WEBHOOK
# =========================
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
        message = "📅 *Сегодня встреч нет* 🎉"
    else:
        message = "📅 *План на сегодня:*\n\n"
        for e in events:
            message += f"{e['start']}–{e['end']} • {e['subject']}\n"

    # сохраняем последний план
    last_plans[email] = message

    send_telegram(chat_id, message, keyboard=main_menu_keyboard())
    return {"status": "ok"}