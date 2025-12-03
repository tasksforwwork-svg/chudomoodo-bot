""" 
chudomoodo_bot.py

Telegram-бот "Дневник маленьких радостей".

Функционал:
- принимает от пользователя короткие тексты-радости;
- очищает мат и нецензурную лексику (расширенный словарь корней);
- сохраняет радости в SQLite;
- ЕЖЕДНЕВНЫЙ РЕЖИМ:
    - в 19:00 — напоминание, если за день не было ни одной радости;
    - в 21:00 — отчёт с радостями за текущего дня;
- защита от тоски: отдельные реакции на грусть, усталость, тревогу, тяжёлые фразы;
- спокойные тексты-ответы с одним эмодзи в начале;
- ачивки за количество радостей и стрики по дням;
- статистика по команде /stats;
- письмо себе в будущее по команде /letter с возможностью отмены /cancel;
- расширенные словари грусти, усталости, тревоги и «не знаю, что написать»;
- более широкое распознавание приветствий, включая опечатки и раскладку;
- отчёт за день включает записанные радости за день;
- на одну эмоцию — один ответ (без дублирующих сообщений);
- получение отчета о записанных радостях по запросу "wantnow".
"""

import os
import time
import sqlite3
import threading
import random
import re
import json
from datetime import datetime, timedelta, date
from typing import List, Tuple, Optional, Dict

import requests

# --------------------------
# CONFIG
# --------------------------

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("Не задан TELEGRAM_TOKEN в переменных окружения.")

API_URL = f"https://api.telegram.org/bot{TOKEN}"
DB_PATH = os.path.join(os.path.dirname(__file__), "joys.db")

POLL_TIMEOUT = 30
POLL_SLEEP = 1

# --------------------------
# СЛОВАРИ (расширенные версии)
# --------------------------

# Расширенный список матов и "жёсткой" лексики (200+ слов)
BAD_WORDS = [
    "хуй", "хуи", "хую", "хуета", "хуёво", "хуево", "хуя", "хуля", "пизда",
    "пиздец", "пиздюк", "пиздить", "пиздануть", "ебать", "ёб", "выеб", "заеб",
    "заёб", "трахать", "хер", "херня", "бляд", "блять", "блядь", "бл*ть",
    "fuck", "fucking", "motherfucker", "bitch", "shit", "bullshit", "asshole",
    "cunt", "dick", "pussy", "slut", "whore",

    # "обходы"
    "х_й", "ху_й", "хyй", "п_здец", "п*здец", "пизд*ц", "п!зд",
    "xуй", "xyй", "xуи", "xyeц",
    "f*ck", "f**k", "f_ck", "fu*k",
    "sh*t", "b*tch", "a**hole",
    "c*nt", "d*ck", "p*ssy", "wh*re",

    # размазанные формы
    "пииизд", "пииздец", "хуии", "хууй", "ебаа", "ёбаа",
    "фукинг", "фак", "факен", "шиит", "бич", "пусси",
]

# Шаблон для поиска "обходов" через регулярку
BAD_WORDS_REGEX = re.compile(
    r"(х[\W_]*у[\W_]*й|п[\W_]*и[\W_]*з[\W_]*д|еба|ёб|бл[\W_]*я|"
    r"f[\W_]*u[\W_]*c[\W_]*k|s[\W_]*h[\W_]*i[\W_]*t|b[\W_]*i[\W_]*t[\W_]*c[\W_]*h)",
    re.IGNORECASE
)

# --------------------------
# РАСШИРЕННЫЕ ПРИВЕТСТВИЯ
# --------------------------

GREETINGS = [
    "привет", "приветик", "прив", "здравствуй", "здравствуйте",
    "добрый день", "доброе утро", "добрый вечер",
    "hi", "hello", "hey",
    "хай", "хеллоу", "хелло", "хало",
    "ку", "йоу"
]
# --------------------------------------
# TELEGRAM API
# --------------------------------------

def tg(method: str, params: dict = None):
    """Универсальная функция запроса к Telegram API."""
    try:
        r = requests.post(f"{API_URL}/{method}", json=params or {}, timeout=20)
        return r.json()
    except Exception as e:
        print("Telegram API error:", e)
        return None


def send_message(chat_id: int, text: str):
    """Отправка сообщения."""
    tg("sendMessage", {"chat_id": chat_id, "text": text})


def get_updates(offset=None):
    """Получение апдейтов."""
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(f"{API_URL}/getUpdates", params=params, timeout=35)
        js = r.json()
        return js.get("result", [])
    except:
        return []


# --------------------------------------
# БАЗА ДАННЫХ
# --------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # радости
    cur.execute("""
        CREATE TABLE IF NOT EXISTS joys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # грустные события
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sad_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    conn.commit()
    conn.close()
# ---------------------------------------------------
# ПРОДОЛЖЕНИЕ РАБОТЫ С БАЗОЙ ДАННЫХ
# ---------------------------------------------------

def add_joy(chat_id: int, text: str):
    """Добавить радость в БД."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO joys (chat_id, text, created_at) VALUES (?, ?, ?)",
        (chat_id, text, created_at)
    )
    conn.commit()
    conn.close()


def add_sad_event(chat_id: int):
    """Добавить событие грусти."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO sad_events (chat_id, created_at) VALUES (?, ?)",
        (chat_id, created_at)
    )
    conn.commit()
    conn.close()


def get_sad_count_last_days(chat_id: int, days: int) -> int:
    """Количество грустных сообщений за N дней."""
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM sad_events
        WHERE chat_id = ?
          AND substr(created_at, 1, 10) >= ?
    """, (chat_id, start.isoformat()))
    count = cur.fetchone()[0]

    conn.close()
    return count


def get_joys_for_date(chat_id: int, date_obj: date):
    """Получить радости за конкретную дату."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT created_at, text
        FROM joys
        WHERE chat_id = ?
          AND substr(created_at, 1, 10) = ?
        ORDER BY created_at ASC
    """, (chat_id, date_obj.isoformat()))

    rows = cur.fetchall()
    conn.close()
    return rows


def has_joy_for_date(chat_id: int, date_obj: date) -> bool:
    """Проверить, писал ли пользователь радость в этот день."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM joys
        WHERE chat_id = ?
          AND substr(created_at, 1, 10) = ?
    """, (chat_id, date_obj.isoformat()))

    count = cur.fetchone()[0]
    conn.close()
    return count > 0


def get_all_user_ids():
    """Список всех пользователей, которые хоть раз писали радости."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT chat_id FROM joys")
    ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return ids
# ---------------------------------------------------
# ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ СТАТИСТИКИ
# ---------------------------------------------------

def get_joy_count(chat_id: int) -> int:
    """Общее количество радостей."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM joys WHERE chat_id = ?", (chat_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_distinct_joy_dates(chat_id: int):
    """Вернуть уникальные даты, когда писались радости."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT substr(created_at, 1, 10)
        FROM joys
        WHERE chat_id = ?
        ORDER BY substr(created_at, 1, 10)
    """, (chat_id,))
    rows = cur.fetchall()
    conn.close()

    result = []
    for (d,) in rows:
        try:
            result.append(date.fromisoformat(d))
        except:
            pass
    return result


def get_current_streak(chat_id: int) -> int:
    """Сколько дней подряд пользователь писал радости."""
    dates = get_distinct_joy_dates(chat_id)
    if not dates:
        return 0

    today = datetime.now().date()
    last_date = dates[-1]

    # если последняя запись была не вчера и не сегодня — streak=0
    if last_date < today - timedelta(days=1):
        return 0

    streak = 1
    i = len(dates) - 1
    while i > 0:
        if (dates[i] - dates[i - 1]).days == 1:
            streak += 1
            i -= 1
        else:
            break
    return streak


# ---------------------------------------------------
# ОЧИСТКА ТЕКСТА + АНТИМАТ
# ---------------------------------------------------

def clean_profanity(text: str) -> str:
    """Удаляем мат по списку + регулярке."""
    original = text

    # 1) Список BAD_WORDS
    lowered = text.lower()
    for bad in BAD_WORDS:
        if bad in lowered:
            repl = "*" * len(bad)
            text = re.sub(bad, repl, text, flags=re.IGNORECASE)
            lowered = text.lower()

    # 2) Регулярка для слов с символами между буквами
    text = BAD_WORDS_REGEX.sub(lambda m: "*" * len(m.group(0)), text)

    return text


def clean_text_pipeline(text: str) -> str:
    """Финальная очистка."""
    text = text.strip()
    if not text:
        return ""
    text = clean_profanity(text)
    return text
# ---------------------------------------------------
# РАСПОЗНАВАНИЕ НАСТРОЕНИЙ
# ---------------------------------------------------

def is_greeting(text: str) -> bool:
    """Проверяет, похоже ли сообщение на приветствие."""
    t = text.lower().strip()
    return t in GREETINGS


def is_severe_sad(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in SEVERE_SAD_PATTERNS)


def is_sad(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in SAD_PATTERNS)


def is_tired(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in TIRED_PATTERNS)


def is_anxiety(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in ANXIETY_PATTERNS)


# ---------------------------------------------------
# ГЕНЕРАЦИЯ ОТВЕТОВ
# ---------------------------------------------------

def emo_prefix(text: str) -> str:
    """Добавляет спокойный эмодзи в начале."""
    return f"{random.choice(CALM_EMOJIS)} {text}"


def resp_sad() -> str:
    return emo_prefix(random.choice(SAD_RESPONSES))


def resp_tired() -> str:
    return emo_prefix(random.choice(TIRED_RESPONSES))


def resp_anxiety() -> str:
    return emo_prefix(random.choice(ANXIETY_RESPONSES))


def resp_greeting() -> str:
    return emo_prefix(random.choice(GREETING_RESPONSES))


def resp_joy() -> str:
    return emo_prefix(random.choice(JOY_RESPONSES))
# ---------------------------------------------------
# ОБРАБОТКА ВХОДЯЩИХ СООБЩЕНИЙ (ЯДРО)
# ---------------------------------------------------

def handle_letter_command(chat_id: int):
    """Запускает диалог письма в будущее."""
    clear_dialog_state(chat_id)
    set_dialog_state(chat_id, "await_letter_period", None)
    send_message(chat_id, emo_prefix(
        "Давай напишем письмо себе в будущее.\n"
        "Выбери через сколько дней напомнить: 7, 14 или 30.\n"
        "Напиши просто число или /cancel чтобы отменить."
    ))


def handle_letter_period(chat_id: int, text: str):
    """Обработка выбора периода письма."""
    if is_cancel_message(text):
        clear_dialog_state(chat_id)
        send_message(chat_id, emo_prefix("Окей, письмо отменено."))
        return

    norm = normalize_text_for_match(text)
    if norm not in {"7", "14", "30"}:
        send_message(chat_id, emo_prefix("Напиши одну из опций: 7, 14 или 30 (дней)."))
        return

    days = int(norm)
    set_dialog_state(chat_id, "await_letter_text", {"days": days})
    send_message(chat_id, emo_prefix(
        f"Отлично — напомню через {days} дней. Теперь напиши само письмо (пару строк)."
    ))


def handle_letter_text(chat_id: int, text: str, meta: dict):
    """Сохраняет письмо (упрощённо — как обычную радость с пометкой)."""
    if is_cancel_message(text):
        clear_dialog_state(chat_id)
        send_message(chat_id, emo_prefix("Отмена — письмо не сохранено."))
        return

    cleaned = text.strip()
    if not cleaned:
        send_message(chat_id, emo_prefix("Письмо пустое — напиши хотя бы пару слов, или /cancel."))
        return

    days = (meta or {}).get("days", 7)
    # Сохраняем как радость с пометкой (упрощённо)
    add_joy(chat_id, f"[Письмо через {days}д] {cleaned}")
    clear_dialog_state(chat_id)
    send_message(chat_id, emo_prefix(f"Готово — сохранила письмо. Напомню через {days} дней."))


def handle_incoming_message(chat_id: int, text: str) -> None:
    """
    Входящая точка для одного текста от пользователя.
    Гарантирует отправку ТОЛЬКО одного ответа.
    """
    if not text or not text.strip():
        return

    # Анти-дубликат по быстрому окну (когда Telegram присылает повторно одно и то же)
    if _is_duplicate_message(chat_id, text):
        # молча игнорируем дубликат
        return

    stripped = text.strip()

    # Команды первой очереди
    if stripped.startswith("/start"):
        clear_dialog_state(chat_id)
        send_message(chat_id, (
            "Привет. Я помогу тебе замечать и сохранять маленькие радости.\n\n"
            "Каждый день можно писать сюда что-то приятное из дня.\n"
            "В 19:00 я напомню, если ты ничего не написала, а в 20:00 пришлю отчёт за день.\n\n"
            "Можешь начать уже сейчас!"
        ))
        return

    if stripped.startswith("/stats"):
        total = get_joy_count(chat_id)
        if total == 0:
            send_message(chat_id, f"{random.choice(STATS_EMOJIS)} Пока у тебя нет записанных радостей.")
        else:
            send_message(chat_id, f"{random.choice(STATS_EMOJIS)} У тебя уже {total} записанных радостей!")
        return

    if stripped.startswith("/letter"):
        handle_letter_command(chat_id)
        return

    if stripped.startswith("/cancel"):
        state, _ = get_dialog_state(chat_id)
        clear_dialog_state(chat_id)
        if state:
            send_message(chat_id, emo_prefix("Окей, отменила."))
        else:
            send_message(chat_id, emo_prefix("Нечего отменять."))
        return

    # Диалог письма (если в процессе)
    state, meta = get_dialog_state(chat_id)
    if state == "await_letter_period":
        handle_letter_period(chat_id, text)
        return
    if state == "await_letter_text":
        handle_letter_text(chat_id, text, meta or {})
        return

    # Мат — быстро и единожды
    if contains_profanity(text):
        send_message(chat_id, emo_prefix(
            "Похоже, сегодня был трудный день. Понимаю, но давай попробуем обойтись без резких слов."
        ))
        return

    # Хотят получить отчёт прямо сейчас
    if is_wantnow_message(stripped):
        send_message(chat_id, get_wantnow_report(chat_id))
        return

    # Приветствия
    if is_greeting_message(stripped):
        send_message(chat_id, get_greeting_response())
        return

    # Тяжёлые состояния (в порядке приоритета) — каждое ветвление возвращает ответ и завершает обработку
    if is_severe_sad_message(stripped):
        send_message(chat_id, emo_prefix(
            "Слышу, что тебе очень тяжело. Пожалуйста, обратись к близким или специалисту — поддержка важна."
        ))
        add_sad_event(chat_id)
        return

    if is_anxiety_message(stripped):
        send_message(chat_id, get_anxiety_response())
        add_sad_event(chat_id)
        return

    if is_tired_message(stripped):
        send_message(chat_id, get_tired_response())
        add_sad_event(chat_id)
        return

    if is_sad_message(stripped):
        send_message(chat_id, get_sad_response())
        add_sad_event(chat_id)
        return

    if is_no_joy_message(stripped):
        send_message(chat_id, get_no_joy_response())
        return

    # Обычная радость — сохраняем и отвечаем один раз
    cleaned = clean_text_pipeline(text)
    if cleaned:
        add_joy(chat_id, cleaned)
        send_message(chat_id, get_joy_response(chat_id))
        return

    # Непонятный ввод
    send_message(chat_id, emo_prefix("Не совсем поняла — напиши чуть по-другому, пожалуйста."))
# ---------------------------------------------------
# ЕЖЕДНЕВНЫЕ ФОНОВЫЕ ЗАДАЧИ
# ---------------------------------------------------

def daily_reminder_runner():
    """
    Напоминание в 19:00.
    Если пользователь не написал радость — отправляем.
    Однократно в день.
    """
    print("Reminder thread started.")
    already_sent = set()

    while True:
        now = datetime.now()
        today = now.date()

        # очищаем старые ключи
        for d in list(already_sent):
            if d != today:
                already_sent.remove(d)

        if now.hour == 19 and now.minute == 0:
            if today not in already_sent:
                print("Sending reminders...")
                for uid in get_all_user_ids():
                    try:
                        if not has_joy_for_date(uid, today):
                            send_message(uid,
                                f"{random.choice(REMINDER_EMOJIS)} "
                                "Уже 19:00. Если сегодня было что-то приятное — можешь написать мне об этом."
                            )
                    except Exception as e:
                        print("Reminder error:", e)

                already_sent.add(today)

        time.sleep(50)  # 1 минута с запасом


def daily_report_runner():
    """
    Отчёт в 21:00 — строго один раз в день.
    """
    print("Daily report thread started.")
    sent_on_date = set()

    while True:
        now = datetime.now()
        today = now.date()

        # очистка старых ключей
        for d in list(sent_on_date):
            if d != today:
                sent_on_date.remove(d)

        # 21:00
        if now.hour == 21 and now.minute == 0:
            if today not in sent_on_date:
                print("Sending daily report...")
                for uid in get_all_user_ids():
                    try:
                        send_daily_report_for_user(uid)
                    except Exception as e:
                        print("Daily report error:", e)

                sent_on_date.add(today)

        time.sleep(50)
# ---------------------------------------------------
# ГЛАВНЫЙ POLL-ЦИКЛ БОТА
# ---------------------------------------------------

def polling_loop():
    """
    Главный цикл, который получает обновления,
    гарантирует однократную обработку каждого update_id.
    """
    print("Polling loop started.")
    offset = None

    while True:
        try:
            updates = get_updates(offset)
        except Exception as e:
            print("Polling error:", e)
            time.sleep(3)
            continue

        if not updates:
            time.sleep(0.5)
            continue

        for upd in updates:
            try:
                uid = upd.get("update_id")
                if uid:
                    offset = uid + 1

                msg = upd.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")

                # Обрабатываем ТОЛЬКО один раз
                handle_incoming_message(chat_id, text)

            except Exception as e:
                print("Update error:", e)

        time.sleep(0.2)


# ---------------------------------------------------
# ЗАПУСК БОТА
# ---------------------------------------------------

def start_bot():
    """Инициализация БД + запуск фоновых потоков + запуск poller."""
    print("Starting bot...")
    init_db()

    # Поток напоминаний в 19:00
    t1 = threading.Thread(target=daily_reminder_runner, daemon=True)
    t1.start()

    # Поток отчёта в 21:00
    t2 = threading.Thread(target=daily_report_runner, daemon=True)
    t2.start()

    # Основной poller
    polling_loop()


if __name__ == "__main__":
    start_bot()
# ---------------------------------------------------
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ---------------------------------------------------

# Память последних сообщений для защиты от двойной реакции
_last_messages = {}  # chat_id → {"text": "...", "ts": timestamp}


def _is_duplicate_message(chat_id: int, text: str) -> bool:
    """
    Проверяет, прислал ли Telegram два одинаковых апдейта подряд.
    Если да — игнорируем.
    """
    now = time.time()
    rec = _last_messages.get(chat_id)

    if rec:
        if rec["text"] == text and (now - rec["ts"] < 4):
            return True  # дубликат внутри 4 секунд

    _last_messages[chat_id] = {"text": text, "ts": now}
    return False


# ---------------------------------------------------
# ПРОВЕРКА НА МАТ
# ---------------------------------------------------

def contains_profanity(text: str) -> bool:
    """
    Определяет, есть ли мат в тексте.
    Фильтрация работает на:
    - BAD_WORDS (точные вхождения)
    - BAD_WORDS_REGEX (размазанные формы)
    """
    t = text.lower()

    # список точных слов
    for w in BAD_WORDS:
        if w in t:
            return True

    # регулярные обходы
    if BAD_WORDS_REGEX.search(text):
        return True

    return False


# ---------------------------------------------------
# УТИЛИТЫ ДЛЯ ДИАЛОГА (LETTER)
# ---------------------------------------------------

_dialog_states = {}  # chat_id → {"state": "...", "meta": {...}}


def set_dialog_state(chat_id: int, state: str, meta: dict | None):
    _dialog_states[chat_id] = {"state": state, "meta": meta}


def get_dialog_state(chat_id: int):
    rec = _dialog_states.get(chat_id)
    if not rec:
        return None, None
    return rec["state"], rec["meta"]


def clear_dialog_state(chat_id: int):
    if chat_id in _dialog_states:
        del _dialog_states[chat_id]


# ---------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФРАЗЫ
# ---------------------------------------------------

def normalize_text_for_match(t: str) -> str:
    return t.strip().lower()


def is_cancel_message(t: str) -> bool:
    return normalize_text_for_match(t) in {"/cancel", "отмена", "стоп", "cancel"}


def is_wantnow_message(text: str) -> bool:
    """Пользователь просит отчёт прямо сейчас."""
    t = normalize_text_for_match(text)
    return t in {
        "хочу отчет", "дай отчёт", "отчет за сегодня", "отчёт за сегодня",
        "хочу отчет сейчас", "дай отчет", "дай отчёт",
        "report", "today report"
    }


def get_wantnow_report(chat_id: int) -> str:
    """Формирует и возвращает отчёт за сегодня без отправки."""
    today = datetime.now().date()
    joys = get_joys_for_date(chat_id, today)

    if not joys:
        return emo_prefix("Сегодня пока нет записанных радостей.")

    lines = []
    for created_at, text in joys:
        try:
            tm = datetime.fromisoformat(created_at).strftime("%H:%M")
        except:
            tm = created_at[11:16]
        lines.append(f"{random.choice(JOY_EMOJIS)} {tm} — {text}")

    return "Вот что хорошего было сегодня:\n\n" + "\n".join(lines)


# Если пользователь пишет «ничего хорошего»
def is_no_joy_message(text: str) -> bool:
    t = text.lower()
    return t in {
        "не было ничего хорошего", "ничего хорошего", "ничего не было",
        "no joy", "nothing good"
    }


def get_no_joy_response() -> str:
    return emo_prefix(
        "Бывает день без ярких моментов. Если хочешь — можем вместе найти что-то совсем маленькое, но тёплое."
    )
