from fastapi import FastAPI, Request, Header, HTTPException
import requests
import re
import os
import json
import html

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
# HELPERS
# =========================
def escape_html(text: str) -> str:
    return html.escape(text)

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
        "parse_mode": "HTML"
    }

    if keyboard:
        payload["reply_markup"] = keyboard

    requests.post(url, json=payload, timeout=10)

# =========================
# MESSAGE FORMATTER
# =========================
def format_day_plan(date_label: str, events: list[dict]) -> str:
    if not events:
        return (
            f"📅 <b>План на {date_label}</b>\n\n"
            "Сегодня встреч нет 🎉\n"
            "Можно спокойно поработать."
        )

    lines = [
        f"📅 <b>План на {date_label}</b>\n",
        "━━━━━━━━━━━━━━"
    ]

    for e in events:
        start = escape_html(e.get("start", "??"))
        end = escape_html(e.get("end", ""))
        subject = escape_html(e.get("subject", "Без темы"))
        organizer = e.get("organizer")

        lines.append(f"🕘 {start}–{end}")
        lines.append(f"<b>{subject}</b>")

        if organizer:
            lines.append(f"👤 {escape_html(organizer)}")

        lines.append("")

    lines.append("━━━━━━━━━━━━━━")
    lines.append("⏰ Напоминание придёт за 10 минут")

    return "\n".join(lines)

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
            "Сначала введи <b>корпоративную почту</b> 👇",
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
            f"✅ Почта <b>{escape_html(email)}</b> сохранена.\n\n"
            "Теперь ты можешь:\n"
            "• смотреть план на сегодня\n"
            "• заранее проверять завтрашний день 📆",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    # =========================
    # BUTTONS
    # =========================
    email = next((e for e, cid in users.items() if cid == chat_id), None)

    if text == "📅 План на сегодня":
        if email and "today" in last_plans.get(email, {}):
            send_telegram(chat_id, last_plans[email]["today"], keyboard=main_menu_keyboard())
        else:
            send_telegram(
                chat_id,
                "📅 План на сегодня будет прислан автоматически утром ⏰",
                keyboard=main_menu_keyboard()
            )
        return {"ok": True}

    if text == "📆 План на завтра":
        if email and "tomorrow" in last_plans.get(email, {}):
            send_telegram(chat_id, last_plans[email]["tomorrow"], keyboard=main_menu_keyboard())
        else:
            send_telegram(
                chat_id,
                "📆 План на завтра ещё не синхронизирован ⏳",
                keyboard=main_menu_keyboard()
            )
        return {"ok": True}

    if text == "🔁 Повторить последний план":
        if email and last_plans.get(email):
            plan = last_plans[email].get("today") or last_plans[email].get("tomorrow")
            send_telegram(
                chat_id,
                f"🔁 <b>Последний план</b>\n\n{plan}",
                keyboard=main_menu_keyboard()
            )
        else:
            send_telegram(
                chat_id,
                "🔁 Пока нет сохранённых планов.",
                keyboard=main_menu_keyboard()
            )
        return {"ok": True}

    if text == "⚙️ Настройки":
        send_telegram(
            chat_id,
            "⚙️ <b>Настройки</b>\n\n"
            "Скоро здесь появятся:\n"
            "• время рассылки\n"
            "• таймзона\n"
            "• рабочие дни",
            keyboard=main_menu_keyboard()
        )
        return {"ok": True}

    if text == "ℹ️ Помощь":
        send_telegram(
            chat_id,
            "ℹ️ <b>Помощь</b>\n\n"
            "1️⃣ Введи корпоративную почту\n"
            "2️⃣ Используй кнопки\n"
            "3️⃣ Получай план дня из Outlook 📅",
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
    day = data.get("day", "today")
    raw_events = data.get("events", [])

    # =========================
    # NORMALIZE EVENTS
    # =========================
    events: list[dict] = []

    if isinstance(raw_events, dict) and "body" in raw_events:
        events = raw_events.get("body", [])
    elif isinstance(raw_events, list):
        events = raw_events
    elif isinstance(raw_events, str):
        try:
            parsed = json.loads(raw_events)
            if isinstance(parsed, dict) and "body" in parsed:
                events = parsed["body"]
            elif isinstance(parsed, list):
                events = parsed
        except Exception:
            events = []

    chat_id = users.get(email)
    if not chat_id:
        return {"status": "user not registered"}

    label = "сегодня" if day == "today" else "завтра"
    message = format_day_plan(label, events)

    last_plans.setdefault(email, {})
    last_plans[email][day] = message

    send_telegram(chat_id, message, keyboard=main_menu_keyboard())
    return {"status": "ok"}