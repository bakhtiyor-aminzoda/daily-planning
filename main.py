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

# email -> { "today": str, "tomorrow": str }
last_plans: dict[str, dict[str, str]] = {}

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
        "resize_keyboard": True
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
        last_plans.setdefault(email, {})

        send_telegram(
            chat_id,
            f"✅ Почта *{email}* сохранена.\n\n"
            "Теперь ты можешь:\n"
            "• смотреть план на сегодня\n"
            "• заранее проверять завтрашний день 📆",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    # =========================
    # BUTTONS
    # =========================

    if text == "📅 План на сегодня":
        email = next((e for e, cid in users.items() if cid == chat_id), None)

        if email and "today" in last_plans.get(email, {}):
            send_telegram(
                chat_id,
                last_plans[email]["today"],
                keyboard=main_menu_keyboard()
            )
        else:
            send_telegram(
                chat_id,
                "📅 План на сегодня будет прислан автоматически утром.\n\n"
                "Если рассылка ещё не была — подожди немного 😉",
                keyboard=main_menu_keyboard()
            )
        return {"ok": True}

    if text == "📆 План на завтра":
        email = next((e for e, cid in users.items() if cid == chat_id), None)

        if not email:
            send_telegram(
                chat_id,
                "❌ Сначала введи корпоративную почту через /start",
                keyboard=main_menu_keyboard()
            )
            return {"ok": True}

        if "tomorrow" in last_plans.get(email, {}):
            send_telegram(
                chat_id,
                last_plans[email]["tomorrow"],
                keyboard=main_menu_keyboard()
            )
        else:
            send_telegram(
                chat_id,
                "📆 План на завтра ещё не синхронизирован.\n\n"
                "⏳ Он появится после обновления календаря в Outlook.",
                keyboard=main_menu_keyboard()
            )
        return {"ok": True}

    if text == "🔁 Повторить последний план":
        email = next((e for e, cid in users.items() if cid == chat_id), None)

        if not email or not last_plans.get(email):
            send_telegram(
                chat_id,
                "🔁 Пока нет сохранённых планов.",
                keyboard=main_menu_keyboard()
            )
            return {"ok": True}

        # приоритет: today → tomorrow
        plans = last_plans[email]
        plan = plans.get("today") or plans.get("tomorrow")

        send_telegram(
            chat_id,
            f"🔁 *Последний план:*\n\n{plan}",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    if text == "⚙️ Настройки":
        send_telegram(
            chat_id,
            "⚙️ Настройки скоро будут доступны.\n\n"
            "Планируется:\n"
            "• время рассылки\n"
            "• таймзона\n"
            "• рабочие дни",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    if text == "ℹ️ Помощь":
        send_telegram(
            chat_id,
            "ℹ️ *Как пользоваться ботом:*\n\n"
            "• Введи корпоративную почту\n"
            "• Используй кнопки для управления\n"
            "• Смотри план на сегодня и завтра\n\n"
            "Если что-то пошло не так — напиши /start",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    send_telegram(
        chat_id,
        "🤔 Я тебя не понял. Используй кнопки ниже 👇",
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
    day = data.get("day", "today")  # today | tomorrow

    chat_id = users.get(email)
    if not chat_id:
        return {"status": "user not registered"}

    if not events:
        message = "📅 *Встреч нет* 🎉"
    else:
        title = "📅 *План на сегодня:*" if day == "today" else "📆 *План на завтра:*"
        message = f"{title}\n\n"
        for e in events:
            message += f"{e['start']}–{e['end']} • {e['subject']}\n"

    last_plans.setdefault(email, {})
    last_plans[email][day] = message

    send_telegram(chat_id, message, keyboard=main_menu_keyboard())
    return {"status": "ok"}