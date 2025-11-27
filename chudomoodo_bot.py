import os
import time
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

import requests

# --------------------------
# CONFIG
# --------------------------

# Токен телеграм-бота. Задаётся через переменную окружения TELEGRAM_TOKEN
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise RuntimeError("Не задан TELEGRAM_TOKEN в переменных окружения.")

API_URL = f"https://api.telegram.org/bot{TOKEN}"

# Путь к файлу базы данных
DB_PATH = os.path.join(os.path.dirname(__file__), "joys.db")

# Основной интервал long polling (секунды)
POLL_TIMEOUT = 30
POLL_SLEEP = 1

# ТЕСТОВЫЙ РЕЖИМ:
# True  – после каждой записанной радости запускается таймер,
#         и через 10 минут пользователю отправляется отчёт за неделю.
# False – боевой режим: еженедельный отчёт по расписанию (вс, 19:00).
TEST_MODE = True

# Использовать ли LanguageTool для исправления орфографии/пунктуации.
# Требуется интернет. Публичный endpoint: https://api.languagetool.org/v2/check
USE_LANGTOOL = False
LANGTOOL_URL = "https://api.languagetool.org/v2/check"

# Небольшой список мата/нецензурной лексики (можно расширять)
BAD_WORDS = [
    "хуй", "хуи", "хер", "пизда", "ебать", "ебан", "сука", "бляд", "бля",
]
# Сезонные/праздничные сообщения (ключ: (месяц, день) -> текст)
HOLIDAY_MESSAGES = {
    (1, 1): "С Новым годом! 🎉 Желаю, чтобы новый год принёс много счастья, здоровья и маленьких радостей каждый день!",
    (3, 1): "Сегодня первый день весны 🌷 Пусть в твоей жизни расцветут новые радости!",
    (6, 1): "Сегодня первый день лета ☀️ Пусть это лето будет ярким, тёплым и радостным!",
    (9, 1): "Сегодня первый день осени 🍁 Пусть эта осень подарит тебе много ярких впечатлений!",
    (12, 1): "Сегодня первый день зимы ❄️ Пусть эта зима подарит тебе тепло и уют!",
}
# Множества для отслеживания уже отправленных уведомлений, чтобы не дублировать
already_sent_holiday = set()
reminded_inactive_users = set()

# --------------------------
# Базовые функции работы с Telegram API
# --------------------------

def get_updates(offset: Optional[int] = None, timeout: int = POLL_TIMEOUT) -> List[dict]:
    params = {
        "timeout": timeout,
    }
    if offset is not None:
        params["offset"] = offset
    try:
        resp = requests.get(f"{API_URL}/getUpdates", params=params, timeout=timeout + 5)
        data = resp.json()
        if not data.get("ok"):
            print("getUpdates error:", data)
            return []
        return data.get("result", [])
    except Exception as e:
        print("getUpdates exception:", e)
        return []

def send_message(chat_id: int, text: str):
    try:
        requests.post(
            f"{API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print("sendMessage error:", e)

# --------------------------
# База данных
# --------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS joys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

def add_joy(chat_id: int, text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO joys (chat_id, text, created_at) VALUES (?, ?, ?)",
        (chat_id, text, created_at),
    )
    conn.commit()
    conn.close()

def get_joys_for_week(chat_id: int, week_start: datetime.date) -> List[Tuple[str, str]]:
    """
    Возвращает список (created_at, text) для радостей пользователя
    начиная с week_start (включительно) до сегодняшнего дня.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # created_at хранится как ISO-строка, можно фильтровать по префиксу даты
    start_str = week_start.isoformat()  # 'YYYY-MM-DD'
    cur.execute(
        """
        SELECT created_at, text
        FROM joys
        WHERE chat_id = ?
          AND substr(created_at, 1, 10) >= ?
        ORDER BY created_at ASC
        """,
        (chat_id, start_str),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_all_user_ids() -> List[int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT chat_id FROM joys")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_last_joy_time(chat_id: int) -> Optional[str]:
    """
    Возвращает ISO-дату/время последней сохранённой радости пользователя,
    или None, если у пользователя ещё нет записей.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT MAX(created_at) FROM joys WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return None

# --------------------------
# Очистка текста: мат + орфография
# --------------------------

def clean_profanity(text: str) -> str:
    lower = text.lower()
    for bad in BAD_WORDS:
        if bad in lower:
            # Заменяем все вхождения слова на звёздочки (по длине слова)
            replacement = "*" * len(bad)
            # заменяем регистронезависимо: проходим по исходному тексту посимвольно
            res_chars = []
            i = 0
            while i < len(text):
                segment = text[i:i + len(bad)]
                if segment.lower() == bad:
                    res_chars.append(replacement)
                    i += len(bad)
                else:
                    res_chars.append(text[i])
                    i += 1
            text = "".join(res_chars)
            lower = text.lower()
    return text

def fix_spelling_with_languagetool(text: str) -> str:
    if not USE_LANGTOOL:
        return text
    try:
        resp = requests.post(
            LANGTOOL_URL,
            data={
                "text": text,
                "language": "ru",
            },
            timeout=10,
        )
        data = resp.json()
        matches = data.get("matches", [])
        if not matches:
            return text

        # Применяем замены с конца, чтобы не сбивать индексы
        text_chars = list(text)
        for m in reversed(matches):
            repls = m.get("replacements")
            if not repls:
                continue
            best = repls[0].get("value")
            offset = m.get("offset", 0)
            length = m.get("length", 0)
            # Заменяем соответствующий диапазон
            text_chars[offset: offset + length] = list(best)
        return "".join(text_chars)
    except Exception as e:
        print("LanguageTool error:", e)
        return text

def clean_text_pipeline(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = clean_profanity(text)
    text = fix_spelling_with_languagetool(text)
    return text

# --------------------------
# Логика отчёта
# --------------------------

def send_weekly_report_for_user(chat_id: int):
    """
    Собирает радости пользователя за последние 7 дней
    и отправляет ему еженедельный отчёт.
    Используется в тестовом режиме (через 10 минут после записи радости)
    и может использоваться в еженедельной рассылке.
    """
    today_local = datetime.now().date()
    week_start = today_local - timedelta(days=6)
    joys = get_joys_for_week(chat_id, week_start)

    if not joys:
        # Если за неделю ничего нет — мягко подбадриваем
        send_message(
            chat_id,
            "Пока у меня нет сохранённых радостей за эту неделю. "
            "Попробуй сегодня заметить хоть что-то маленькое и хорошее 🌿",
        )
        return

    lines = []
    for i, (created_at, text) in enumerate(joys, start=1):
        # Можно показывать только текст, без даты, чтобы не перегружать
        lines.append(f"{i}. {text}")

    header = "Посмотри, как много чудесного произошло за эту неделю:"
    body = "\n".join(lines)
    send_message(chat_id, f"{header}\n\n{body}")

# --------------------------
# Обработка входящих сообщений
# --------------------------

def process_incoming_message(update: dict):
    """
    Обрабатывает одно обновление Telegram.
    Нас интересуют только текстовые сообщения от пользователя.
    """
    if "message" not in update:
        return

    msg = update["message"]
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return

    text = msg.get("text", "")
    if not text:
        return

    # Команда /start — приветствие и объяснение
    if text.strip().startswith("/start"):
        send_message(
            chat_id,
            "Привет! Я твой дневник маленьких радостей.\n\n"
            "Каждый день напиши мне одну вещь, которая тебя порадовала: "
            "слово, момент, человека, событие.\n\n"
            "А по итогам недели я напомню тебе, как много хорошего с тобой произошло ✨",
        )
        return
    # Команда /korobochka или /randomjoy — показать случайную сохранённую радость
    if text.strip().lower().startswith("/korobochka") or text.strip().lower().startswith("/randomjoy") or text.strip().lower().startswith("/random"):
        # Ищем случайную радость пользователя в базе данных
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT text, created_at FROM joys WHERE chat_id = ? ORDER BY RANDOM() LIMIT 1", (chat_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            send_message(chat_id, "Твоя коробочка с воспоминаниями пока пуста. Напиши мне свою первую радость, чтобы её сохранить ✨")
        else:
            joy_text, created_at = row
            try:
                joy_date = datetime.fromisoformat(created_at)
                date_str = joy_date.strftime("%d.%m.%Y")
            except Exception as e:
                date_str = created_at.split("T")[0]
            send_message(chat_id, f"Открываем твою коробочку с воспоминаниями 🗃\nЗапись от {date_str}: {joy_text}")
        return

    # Обычный текст — считаем радостью
    cleaned = clean_text_pipeline(text)
    if not cleaned:
        send_message(chat_id, "Кажется, я ничего не смогла сохранить. Напиши ещё раз, ладно? 🌿")
        return

    add_joy(chat_id, cleaned)
    if chat_id in reminded_inactive_users:
        reminded_inactive_users.remove(chat_id)
    send_message(chat_id, "Записала твою маленькую радость ✨ Спасибо!")

    # В ТЕСТОВОМ РЕЖИМЕ: через 10 минут отправляем отчёт за неделю
    if TEST_MODE:
        timer = threading.Timer(600, send_weekly_report_for_user, args=(chat_id,))
        timer.daemon = True
        timer.start()

# --------------------------
# (Опционально) еженедельный отчёт по расписанию
# --------------------------

def scheduled_job_runner():
    print("Scheduled job runner started.")
    already_sent_for_week = set()
    global already_sent_holiday, reminded_inactive_users
    while True:
        now = datetime.now()
        # Еженедельный отчёт (по воскресеньям в 19:00)
        if now.isoweekday() == 7 and now.hour == 19:
            if not TEST_MODE:
                year, week_num, _ = now.isocalendar()
                key = (year, week_num)
                if key not in already_sent_for_week:
                    print("Sending weekly reports...")
                    for user_id in get_all_user_ids():
                        try:
                            send_weekly_report_for_user(user_id)
                        except Exception as e:
                            print(f"Error sending weekly report to {user_id}:", e)
                    already_sent_for_week.add(key)
        # Сезонные/праздничные поздравления (в 09:00 утра, если дата совпадает)
        if now.hour == 9 and now.minute == 0:
            month_day = (now.month, now.day)
            if month_day in HOLIDAY_MESSAGES:
                key = (now.year, now.month, now.day)
                if key not in already_sent_holiday:
                    message = HOLIDAY_MESSAGES[month_day]
                    print(f"Sending holiday message for date {month_day} to all users...")
                    for user_id in get_all_user_ids():
                        try:
                            send_message(user_id, message)
                        except Exception as e:
                            print(f"Error sending holiday message to {user_id}:", e)
                    already_sent_holiday.add(key)
        # Напоминание об отсутствии активности (в 11:00, если пользователь не писал 3 дня)
        if now.hour == 11 and now.minute == 0:
            cutoff = now - timedelta(days=3)
            for user_id in get_all_user_ids():
                last_time_str = get_last_joy_time(user_id)
                if not last_time_str:
                    continue
                try:
                    last_time = datetime.fromisoformat(last_time_str)
                except Exception as e:
                    try:
                        last_time = datetime.fromisoformat(last_time_str.split(".")[0])
                    except Exception as e:
                        continue
                if last_time < cutoff:
                    if user_id not in reminded_inactive_users:
                        print(f"Sending inactivity reminder to user {user_id}")
                        send_message(user_id, "Привет! Ты давно не делился радостями — надеюсь, у тебя всё хорошо. Может, расскажешь о какой-нибудь радости, что случилась с тобой недавно? 🌸")
                        reminded_inactive_users.add(user_id)
        time.sleep(60)

def main():
    init_db()

    # Запускаем фоновый поток для плановых уведомлений
    t = threading.Thread(target=scheduled_job_runner, daemon=True)
    t.start()

    offset = None
    print("ChudoMoodo bot polling started...")
    while True:
        updates = get_updates(offset=offset, timeout=POLL_TIMEOUT)
        for upd in updates:
            try:
                offset = max(offset or 0, upd["update_id"] + 1)
                process_incoming_message(upd)
            except Exception as e:
                print("process error:", e)
        time.sleep(POLL_SLEEP)

if __name__ == "__main__":
    main()
