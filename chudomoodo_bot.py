"""
chudomoodo_bot.py

Telegram-бот "Дневник маленьких радостей" (ChudoMoodo / FeelMeter).

Функции:
- принимает от пользователя короткие тексты-радости;
- очищает мат и нецензурную лексику;
- при желании может исправлять орфографию и пунктуацию через LanguageTool (онлайн);
- сохраняет радости в SQLite;
- в ТЕСТОВОМ РЕЖИМЕ: через 10 минут после записи радости
  отправляет пользователю список радостей за неделю
  с текстом "Посмотри, как много чудесного произошло за эту неделю".

Требуется: requests
"""

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
# False – можно будет включить классический еженедельный отчёт по расписанию.
TEST_MODE = True

# Использовать ли LanguageTool для исправления орфографии/пунктуации.
# Требуется интернет. Публичный endpoint: https://api.languagetool.org/v2/check
USE_LANGTOOL = False
LANGTOOL_URL = "https://api.languagetool.org/v2/check"

# Небольшой список мата/нецензурной лексики (можно расширять)
BAD_WORDS = [
    "хуй", "хуи", "хер", "пизда", "ебать", "ебан", "сука", "бляд", "бля",
]

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
    # Создаём новую таблицу для хранения воспоминаний
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
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

# Новые функции для работы с "коробочкой воспоминаний"
def add_memory(chat_id: int, text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute("INSERT INTO memories (chat_id, text, created_at) VALUES (?, ?, ?)", (chat_id, text, created_at))
    conn.commit()
    conn.close()

def get_joys_for_day(chat_id: int, date: datetime.date) -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    start_str = date.isoformat()
    next_day = date + timedelta(days=1)
    next_str = next_day.isoformat()
    cur.execute("SELECT text FROM joys WHERE chat_id = ? AND created_at >= ? AND created_at < ?", (chat_id, start_str, next_str))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_random_memories(chat_id: int, max_count: int = 3) -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT text FROM memories WHERE chat_id = ? ORDER BY RANDOM() LIMIT ?", (chat_id, max_count))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_all_user_ids() -> List[int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT chat_id FROM joys")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

# --------------------------
# Глобальный словарь для функции 'коробочка воспоминаний'
# --------------------------
pending_memory = {}

# --------------------------
# Обработка входящих сообщений
# --------------------------

def process_incoming_message(msg):
    # Only handle text messages
    if "message" not in msg:
        return
    m = msg["message"]
    if "text" not in m:
        return
    text = m["text"].strip()
    chat_id = m["chat"]["id"]
    # commands
    if text.startswith("/start"):
        send_message(chat_id, "Привет! Я ChudoMoodo — пришли мне одну маленькую радость в день. В воскресенье в 19:00 я пришлю итог недели.")
        return
    if text.startswith("/week"):
        # send last week's joys (based on current local week start)
        today_local = datetime.now().date()
        last_sunday = today_local - timedelta(days=(today_local.weekday()+1) % 7)  # last Sunday or today if Sunday
        week_start = last_sunday - timedelta(days=6)
        joys = get_joys_for_week(chat_id, week_start)
        if not joys:
            send_message(chat_id, "Пока нет записей за прошлую неделю.")
            return
        lines = [f"{i+1}. {j[1]}" for i, j in enumerate(joys)]
        header = "Посмотри, как много чудесного произошло за эту неделю:"
        send_message(chat_id, header + "\n\n" + "\n".join(lines))
        return

    # Обработчик команды "/memories" и запроса "Напомнить о всем хорошем"
    if text.startswith("/memories") or text.lower().replace("ё", "е") in ["напомнить о всем хорошем", "напомни о всем хорошем"]:
        mems = get_random_memories(chat_id)
        if not mems:
            send_message(chat_id, "Твоя коробочка воспоминаний пока пуста. Давай наполнять её радостными моментами каждый день! 😊")
        else:
            lines = [f"✨ {m}" for m in mems]
            message = "Посмотри, какие чудесные воспоминания хранятся в твоей коробочке:\n\n" + "\n".join(lines)
            send_message(chat_id, message)
        return

    # Если бот ожидает ответ для "коробочки воспоминаний"
    if chat_id in pending_memory:
        info = pending_memory.get(chat_id, {})
        if info.get("date") and info["date"] != datetime.now().date():
            pending_memory.pop(chat_id, None)
        else:
            user_input = text.strip()
            if user_input.lower() in ["нет", "не надо", "не нужно", "no"]:
                send_message(chat_id, "Хорошо, ничего не сохраняю 🙂")
                pending_memory.pop(chat_id, None)
                return
            memory_text = None
            joys_list = info.get("joys", [])
            if joys_list:
                if user_input.isdigit():
                    idx = int(user_input)
                    if 1 <= idx <= len(joys_list):
                        memory_text = joys_list[idx - 1]
                    else:
                        memory_text = user_input
                elif user_input.lower() in ["да", "yes"]:
                    if len(joys_list) == 1:
                        memory_text = joys_list[0]
                    else:
                        memory_text = joys_list[0]
                else:
                    memory_text = user_input
                add_to_joys = False
            else:
                memory_text = user_input
                add_to_joys = True
            if memory_text:
                cleaned_mem = clean_text_pipeline(memory_text)
                if add_to_joys:
                    add_joy(chat_id, cleaned_mem)
                add_memory(chat_id, cleaned_mem)
                if add_to_joys:
                    send_message(chat_id, "Спасибо, я добавила это хорошее воспоминание в твою коробочку ✨")
                else:
                    send_message(chat_id, "Я добавила это воспоминание в твою коробочку ✨")
            pending_memory.pop(chat_id, None)
            return

    # normal text: save joy (limit 1 per day)
    last_date = get_last_entry_date(chat_id)  # (предполагается, что эта функция уже есть в коде)
    today_local = datetime.now().date()
    if last_date == today_local:
        send_message(chat_id, "У тебя уже есть запись на сегодня — приходи завтра или напиши /week чтобы увидеть свои записи.")
        return

    # clean pipeline
    cleaned = clean_text_pipeline(text)
    # save to DB
    add_joy(chat_id, cleaned)
    send_message(chat_id, "Записала твою радость ✨ Спасибо!")

# --------------------------
# Фоновая задача для ежедневных напоминаний
# --------------------------

def daily_job_runner():
    print("Daily job runner started.")
    last_sent_date = None
    while True:
        now = datetime.now()
        if now.hour == 21 and (last_sent_date is None or last_sent_date != now.date()):
            for uid in get_all_user_ids():
                joys_today = get_joys_for_day(uid, now.date())
                if joys_today:
                    lines = []
                    for i, text in enumerate(joys_today, start=1):
                        lines.append(f"{i}. {text}")
                    joys_list = "\n".join(lines)
                    message = ("День подходит к концу. Давай выберем, какое из сегодняшних радостных событий "
                               "мы положим в твою коробочку воспоминаний.\n")
                    message += "Сегодня ты отмечал(а):\n" + joys_list + "\n\n"
                    message += "Отправь мне номер или текст того, что хочешь сохранить 🧡"
                else:
                    message = ("День подходит к концу. У тебя сегодня пока нет записанной радости. "
                               "Может быть, хочешь поделиться чем-то хорошим, что произошло? "
                               "Я сохраню это в твоей коробочке воспоминаний 🧡")
                send_message(uid, message)
                pending_memory[uid] = {"joys": joys_today or [], "date": now.date()}
            last_sent_date = now.date()
        time.sleep(60)

# --------------------------
# Weekly job (еженедельная задача)
# --------------------------

def weekly_job_runner():
    # ... (остается без изменений)
    # (Код еженедельной задачи сокращен для краткости)
    while True:
        # ... (условие и рассылка еженедельного отчёта)
        time.sleep(60)

# --------------------------
# Main loop
# --------------------------

def main():
    init_db()
    # start weekly background thread
    if not TEST_MODE:
        t = threading.Thread(target=weekly_job_runner, daemon=True)
        t.start()
        # start daily background thread
        d = threading.Thread(target=daily_job_runner, daemon=True)
        d.start()

    offset = None
    print("ChudoMoodo bot polling started...")
    while True:
        updates = get_updates(offset=offset, timeout=30)
        for upd in updates:
            offset = max(offset or 0, upd["update_id"] + 1)
            try:
                process_incoming_message(upd)
            except Exception as e:
                print("process error:", e)
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
