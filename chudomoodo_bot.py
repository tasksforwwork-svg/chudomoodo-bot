"""
chudomoodo_bot.py

Telegram-бот "Дневник маленьких радостей".
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

USE_LANGTOOL = False
LANGTOOL_URL = "https://api.languagetool.org/v2/check"

# --------------------------
# СЛОВАРИ
# --------------------------

BAD_WORDS = [
    "хуй", "хуи", "хуе", "хуё", "хуя", "хуем", "хуйн", "хуит", "хуяр",
    "хер", "хрен", "хрена", "хренов", "хренот", "хренотень",
    "пизд", "пизда", "пиздец", "пезд", "пидор", "пидар", "педрила",
    "еба", "ебу", "ебё", "ебе", "ебан", "ёбн", "ебло", "ебальн", "выеб",
    "еблись", "ебуч", "ебанут", "доеб", "заеб", "заёб", "заипал", "заипали",
    "сука", "суки", "сучк", "сучар", "сучонок",
    "бляд", "бля", "блят", "бляха", "бляха-муха", "бляха муха",
    "мразь", "тварь", "тварн", "скотина", "ублюд", "уебк", "уёбк",
    "гандон", "презик", "конча", "конченный", "конченый",
    "хуйня", "хуёв", "хренот", "говно", "говн", "дерьм", "срака",
    "сука-блять", "сука блять",
    "долбоеб", "долбоёб", "дебил", "идиот", "кретин", "мудак", "мудила",
    "чмо", "чмошн", "козлина", "урод", "уродин",
    "шлюх", "проститут", "шалав", "траха", "трахну",
    "срать", "срал", "насрать", "насрал",
    "бесишь", "морда кирпичом", "иди в жопу", "пошел в жопу", "пошла в жопу",
]

SAD_PATTERNS = [
    "ничего хорошего не было", "ничего хорошего сегодня не было",
    "ничего хорошего", "ничего не радует", "ничто не радует",
    "всё плохо", "все плохо", "все ужасно", "всё ужасно", "совсем плохо",
    "ужасный день", "отвратительный день", "день говно", "день отстой",
    "день был ужасный", "день не задался", "день коту под хвост",
    "всё бесит", "все бесит", "все раздражает", "всё раздражает",
    "плохо", "очень плохо", "крайне плохо",
    "тяжело", "очень тяжело", "душно внутри",
    "грустно", "очень грустно", "мне грустно", "мне очень грустно",
]

TIRED_PATTERNS = [
    "устала", "устал", "я так устала", "я так устал",
    "очень устала", "очень устал",
    "сильно устала", "сильно устал",
    "сегодня вообще без сил", "сегодня нет сил",
    "сил нет", "нет сил", "ни на что нет сил",
    "совсем нет сил", "ни капли сил",
]

ANXIETY_PATTERNS = [
    "боюсь", "очень боюсь", "безумно боюсь",
    "мне страшно", "страшно", "дико страшно",
    "переживаю", "очень переживаю", "сильно переживаю",
    "я переживаю", "я опять переживаю",
    "тревожно", "очень тревожно", "дико тревожно",
    "меня трясет", "меня трясёт",
    "паника", "паническую", "панически", "паническая атака",
]

SEVERE_SAD_PATTERNS = [
    "не хочу жить", "не хочу больше жить",
    "нет смысла жить", "не вижу смысла жить",
    "не вижу смысла", "нет смысла",
    "жизнь бессмысленна", "жизнь не имеет смысла",
    "ненавижу свою жизнь", "ненавижу жизнь",
    "хочу умереть", "хочу просто исчезнуть",
]

NO_JOY_PATTERNS = [
    "не знаю что написать", "не знаю, что написать",
    "не знаю что писать", "не знаю, что писать",
    "нечего писать", "нечего сказать", "нечего добавлять",
    "ничего не могу вспомнить", "ничего не запомнилось",
    "ничего хорошего не было", "ничего радостного не было",
]

CANCEL_PATTERNS = [
    "отмена", "отменить",
    "я передумала", "я передумал",
    "не хочу писать", "не хочу письмо",
    "/cancel",
]

GREETING_PATTERNS = [
    "привет", "привет!", "приветик", "приветики",
    "привет)", "привет))", "приветствую",
    "здравствуй", "здравствуйте", "здравствуйте)",
    "добрый день", "добрый вечер", "доброе утро", "доброй ночи",
    "хай", "хай!", "хай)", "хэй", "хей", "хелло", "хеллоу",
    "hello", "hi", "hey",
]

GREETING_RESPONSES = [
    "Привет. Как твой день? Расскажешь что-нибудь хорошее, даже если оно совсем маленькое?",
    "Привет, я тут. Можешь скинуть одну радость за сегодня — даже если это просто вкусный чай.",
    "Рада тебя видеть здесь. Давай отметим что-нибудь приятное из этого дня?",
]

JOY_EMOJIS = ["✨", "😊", "🌈", "💛", "🌟"]
REMINDER_EMOJIS = ["✨", "📌", "😊"]
STATS_EMOJIS = ["📊", "📈", "⭐"]
CALM_EMOJIS = ["🙂", "🌿", "✨", "☕", "🕊", "🍃"]

SAD_RESPONSES = [
    "Звучит как очень непростой день. Не обязательно прямо сейчас искать в нём плюсы.\n\n"
    "Если позже вспомнишь момент, где стало хоть немного легче — напиши, я бережно его сохраню.",

    "Понимаю, что сегодня могло быть тяжко.\n\n"
    "Иногда единственное хорошее — это то, что день закончился. А если вдруг всплывёт что-то чуть мягче — я здесь.",
]

TIRED_RESPONSES = [
    "Похоже, день тебя основательно выжал.\n\n"
    "Это не про слабость, а про то, что ты слишком много тащишь. Если вспомнишь момент, где стало хоть на полтона легче — напиши.",
]

ANXIETY_RESPONSES = [
    "Чувствуется тревога. Обычно она про то, что для тебя важно, а не про слабость.\n\n"
    "Попробуй вспомнить момент, когда внутри стало хоть немного тише — я с радостью его сохраню.",
]

NO_JOY_RESPONSES = [
    "Бывает, что день будто пустой. Можно ничего не выжимать из себя. Если позже всплывёт что-то тёплое — просто напиши.",
]

JOY_RESPONSES = [
    "Сохранила это в копилку хороших моментов.",
    "Записала. Пусть это будет маленькой опорой на твой день.",
    "Оставила этот момент здесь — чтобы он не потерялся в суете.",
]

LAST_JOY_INDEX: dict[int, int] = {}

# --------------------------
# Telegram API
# --------------------------

def get_updates(offset: Optional[int] = None, timeout: int = POLL_TIMEOUT) -> List[dict]:
    params = {"timeout": timeout}
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
# DB
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sad_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS dialog_state (
            chat_id INTEGER PRIMARY KEY,
            state TEXT NOT NULL,
            meta TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS future_letters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            send_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent INTEGER NOT NULL DEFAULT 0
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


def add_sad_event(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO sad_events (chat_id, created_at) VALUES (?, ?)",
        (chat_id, created_at),
    )
    conn.commit()
    conn.close()


def get_joy_count(chat_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM joys WHERE chat_id = ?",
        (chat_id,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def has_joy_for_date(chat_id: int, date_obj: date) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    date_str = date_obj.isoformat()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM joys
        WHERE chat_id = ?
          AND substr(created_at, 1, 10) = ?
        """,
        (chat_id, date_str),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


def get_all_user_ids() -> List[int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT chat_id FROM joys")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def set_dialog_state(chat_id: int, state: str, meta: Optional[dict] = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    meta_json = json.dumps(meta) if meta is not None else None
    cur.execute(
        """
        INSERT INTO dialog_state (chat_id, state, meta, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            state = excluded.state,
            meta = excluded.meta,
            updated_at = excluded.updated_at
        """,
        (chat_id, state, meta_json, now),
    )
    conn.commit()
    conn.close()


def get_dialog_state(chat_id: int) -> Tuple[Optional[str], Optional[dict]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT state, meta FROM dialog_state WHERE chat_id = ?",
        (chat_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None, None
    state, meta_json = row
    meta = None
    if meta_json:
        try:
            meta = json.loads(meta_json)
        except Exception:
            meta = None
    return state, meta


def clear_dialog_state(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM dialog_state WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


# --------------------------
# Очистка текста и проверка мата
# --------------------------

def normalize_text_for_match(text: str) -> str:
    lower = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^\w\s]+", " ", lower)
    normalized = " ".join(normalized.split())
    return normalized


def contains_profanity(text: str) -> bool:
    """Проверяет, содержит ли текст мат"""
    normalized = normalize_text_for_match(text)
    for bad_word in BAD_WORDS:
        if bad_word in normalized:
            return True
    return False


def clean_profanity(text: str) -> str:
    """Очищает мат из текста"""
    words = text.split()
    cleaned_words = []
    
    for word in words:
        lower_word = word.lower()
        word_cleaned = False
        
        for bad_root in BAD_WORDS:
            if bad_root in lower_word:
                cleaned_word = ""
                for char in word:
                    if char.isalpha():
                        cleaned_word += "*"
                    else:
                        cleaned_word += char
                cleaned_words.append(cleaned_word)
                word_cleaned = True
                break
        
        if not word_cleaned:
            cleaned_words.append(word)
    
    return " ".join(cleaned_words)


def clean_text_pipeline(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = clean_profanity(text)
    return text


# --------------------------
# Распознавание состояний
# --------------------------

def is_severe_sad_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    return any(p in lower for p in SEVERE_SAD_PATTERNS)


def is_sad_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    return any(p in lower for p in SAD_PATTERNS)


def is_tired_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    return any(p in lower for p in TIRED_PATTERNS)


def is_anxiety_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    return any(p in lower for p in ANXIETY_PATTERNS)


def is_no_joy_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    return any(p in lower for p in NO_JOY_PATTERNS)


def is_cancel_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    return any(p in lower for p in CANCEL_PATTERNS)


def is_greeting_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    if len(lower) > 40:
        return False
    for p in GREETING_PATTERNS:
        if lower == p or lower.startswith(p) or f" {p} " in f" {lower} ":
            return True
    return False


# --------------------------
# Генерация ответов
# --------------------------

def add_emoji_prefix(text: str) -> str:
    return f"{random.choice(CALM_EMOJIS)} {text}"


def get_sad_response() -> str:
    return add_emoji_prefix(random.choice(SAD_RESPONSES))


def get_tired_response() -> str:
    return add_emoji_prefix(random.choice(TIRED_RESPONSES))


def get_anxiety_response() -> str:
    return add_emoji_prefix(random.choice(ANXIETY_RESPONSES))


def get_greeting_response() -> str:
    return add_emoji_prefix(random.choice(GREETING_RESPONSES))


def get_no_joy_response() -> str:
    return add_emoji_prefix(random.choice(NO_JOY_RESPONSES))


def get_joy_response(chat_id: int) -> str:
    if not JOY_RESPONSES:
        return add_emoji_prefix("Записала это как твою радость.")
    last_idx = LAST_JOY_INDEX.get(chat_id)
    idx = random.randrange(len(JOY_RESPONSES))
    if last_idx is not None and len(JOY_RESPONSES) > 1:
        for _ in range(3):
            if idx != last_idx:
                break
            idx = random.randrange(len(JOY_RESPONSES))
    LAST_JOY_INDEX[chat_id] = idx
    return add_emoji_prefix(JOY_RESPONSES[idx])


# --------------------------
# Обработка входящих сообщений
# --------------------------

def process_incoming_message(update: dict):
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

    stripped = text.strip()

    # Глобальная отмена
    if stripped.startswith("/cancel"):
        state, _ = get_dialog_state(chat_id)
        clear_dialog_state(chat_id)
        if state in ("await_letter_period", "await_letter_text"):
            send_message(
                chat_id,
                add_emoji_prefix(
                    "Окей, письмо себе пока отложим. Если захочешь вернуться — напиши /letter."
                )
            )
        else:
            send_message(
                chat_id,
                add_emoji_prefix(
                    "Отменила текущий диалог. Можно просто продолжить писать радости, когда захочется."
                )
            )
        return

    # Команды
    if stripped.startswith("/start"):
        clear_dialog_state(chat_id)
        send_message(
            chat_id,
            "Привет. Я помогу тебе замечать и сохранять маленькие радости.\n\n"
            "Каждый день можно писать сюда что-то приятное из дня: встречу, вкусный кофе, спокойный вечер.\n"
            "В 18:00 я напомню, если ты ничего не написала, а в 21:00 пришлю небольшой отчёт за день.\n\n"
            "А ещё здесь можно написать письмо себе в будущее — для этого есть команда /letter.\n"
            "Если вдруг по ходу диалога или письма ты передумаешь — просто напиши /cancel.\n\n"
            "Можешь начать уже сейчас: напиши одну маленькую радость или тёплый момент из этого дня."
        )
        return

    if stripped.startswith("/stats"):
        total = get_joy_count(chat_id)
        if total == 0:
            send_message(
                chat_id,
                f"{random.choice(STATS_EMOJIS)} Пока у тебя нет записанных радостей.\n"
                "Можно начать с одной небольшой, когда почувствуешь ресурс."
            )
        else:
            send_message(
                chat_id,
                f"{random.choice(STATS_EMOJIS)} У тебя уже {total} записанных радостей!\n"
                "Это замечательно, что ты замечаешь хорошее в своих днях."
            )
        return

    # Проверка на мат ДО любой другой обработки
    if contains_profanity(text):
        send_message(
            chat_id,
            add_emoji_prefix("Похоже, сегодня был трудный день! Понимаю, но давай попробуем обойтись без резких слов")
        )
        return

    # Состояние диалога
    state, meta = get_dialog_state(chat_id)

    # Приветствие — отвечаем, но НЕ записываем как радость
    if is_greeting_message(stripped):
        send_message(chat_id, get_greeting_response())
        return

    # Очень тяжёлые сообщения
    if is_severe_sad_message(stripped):
        send_message(
            chat_id,
            add_emoji_prefix(
                "Слышу, что тебе сейчас очень тяжело.\n\n"
                "С такими чувствами не обязательно справляться одной. "
                "Постарайся поговорить с тем, кому доверяешь: близкий человек, друг, специалист.\n"
                "Ты важна и имеешь право на поддержку."
            )
        )
        add_sad_event(chat_id)
        return

    # Тревога
    if is_anxiety_message(stripped):
        send_message(chat_id, get_anxiety_response())
        add_sad_event(chat_id)
        return

    # Усталость
    if is_tired_message(stripped):
        send_message(chat_id, get_tired_response())
        add_sad_event(chat_id)
        return

    # Грусть
    if is_sad_message(stripped):
        send_message(chat_id, get_sad_response())
        add_sad_event(chat_id)
        return

    # Нейтральное "не знаю, что написать" — не сохраняем, просто отвечаем
    if is_no_joy_message(stripped):
        send_message(chat_id, get_no_joy_response())
        return

    # Обычная радость
    cleaned = clean_text_pipeline(text)
    if not cleaned:
        send_message(
            chat_id,
            "Мне не удалось ничего сохранить.\n"
            "Попробуй написать чуть конкретнее, что тебя сегодня порадовало."
        )
        return

    add_joy(chat_id, cleaned)
    send_message(chat_id, get_joy_response(chat_id))


# --------------------------
# Ежедневные напоминания
# --------------------------

def daily_reminder_runner():
    print("Daily reminder runner started.")
    reminded_dates = set()
    while True:
        now = datetime.now()
        today = now.date()
        for d in list(reminded_dates):
            if d != today:
                reminded_dates.remove(d)
        if now.hour == 18 and now.minute == 0:
            if today not in reminded_dates:
                print("Sending daily reminders...")
                for user_id in get_all_user_ids():
                    try:
                        if not has_joy_for_date(user_id, today):
                            emo = random.choice(REMINDER_EMOJIS)
                            send_message(
                                user_id,
                                f"{emo} Уже 18:00.\n"
                                "Очень вероятно, что сегодня был хотя бы один небольшой хороший момент. "
                                "Давай не дадим ему потеряться — напиши мне о нём."
                            )
                    except Exception as e:
                        print(f"Error sending daily reminder to {user_id}:", e)
                reminded_dates.add(today)
        time.sleep(60)


# --------------------------
# main
# --------------------------

def main():
    init_db()

    t_daily_reminder = threading.Thread(target=daily_reminder_runner, daemon=True)
    t_daily_reminder.start()

    offset = None
    print("ChudoMoodo bot polling started...")
    while True:
        try:
            updates = get_updates(offset=offset, timeout=POLL_TIMEOUT)
            for upd in updates:
                try:
                    offset = max(offset or 0, upd["update_id"] + 1)
                    process_incoming_message(upd)
                except Exception as e:
                    print("process error:", e)
            time.sleep(POLL_SLEEP)
        except Exception as e:
            print("main loop error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
