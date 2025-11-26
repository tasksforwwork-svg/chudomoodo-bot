"""
chudomoodo_bot.py

Telegram-бот "Дневник маленьких радостей".

Функционал:
- принимает от пользователя короткие тексты-радости;
- очищает мат и нецензурную лексику;
- (опционально) исправляет орфографию и пунктуацию через LanguageTool;
- сохраняет радости в SQLite;
- ЕЖЕДНЕВНЫЙ РЕЖИМ:
    - в 19:00 — напоминание, если за день не было ни одной радости;
    - в 22:00 — отчёт с радостями за текущий день;
- защита от тоски: отдельные реакции на грусть, усталость, тревогу, тяжёлые фразы;
- спокойные тексты-ответы с одним эмодзи в начале;
- ачивки за количество радостей и стрики по дням (без упора на цифры в формулировках);
- статистика по команде /stats;
- ритуал «3 маленькие радости», если много грусти;
- микродиалоги: бот может попросить найти одну маленькую опору;
- персонализация по темам радостей (еда, люди, природа, отдых, успехи);
- недельные и месячные обзоры по-человечески;
- письма себе в будущее по команде /letter (через 7 / 14 / 30 дней).
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

BAD_WORDS = [
    "хуй", "хуи", "хер", "пизда", "ебать", "ебан", "сука", "бляд", "бля",
]

SAD_PATTERNS = [
    "ничего хорошего не было",
    "ничего хорошего сегодня не было",
    "ничего хорошего",
    "ничего не радует",
    "ничто не радует",
    "всё плохо",
    "все плохо",
    "ужасный день",
    "отвратительный день",
    "день говно",
    "всё бесит",
    "все бесит",
    "плохо",
    "тяжело",
    "грустно",
    "хреново",
    "депрессивно",
    "ничего не хочется",
    "не хочу ничего",
    "нет настроения",
    "день был ужасный",
    "ничего нормального",
    "ужас",
    "разочарование",
    "меня никто не понимает",
    "я одна",
    "я один",
    "чувствую себя одиноко",
    "одиночество",
    "мне плохо",
    "мне грустно",
    "я реву",
    "хочу плакать",
    "плакать хочется",
]

TIRED_PATTERNS = [
    "устала",
    "устал",
    "я так устала",
    "я так устал",
    "очень устала",
    "очень устал",
    "сил нет",
    "нет сил",
    "ни на что нет сил",
    "выгорела",
    "выгорел",
    "я выгорела",
    "я выгорел",
    "мне тяжело",
    "очень тяжело",
]

ANXIETY_PATTERNS = [
    "боюсь",
    "мне страшно",
    "страшно",
    "переживаю",
    "я переживаю",
    "тревожно",
    "меня трясет",
    "паника",
    "паникую",
    "вдруг не получится",
    "я не уверена",
    "я неуверенна",
    "я не уверен",
    "волнуюсь",
    "я волнуюсь",
    "я все испортила",
    "я все испортил",
    "боюсь ошибиться",
]

# Нейтральные фразы "не знаю, что написать"
NO_JOY_PATTERNS = [
    "не знаю что написать",
    "не знаю что добавить",
    "не знаю что сказать",
    "не могу ничего придумать",
    "не могу придумать",
    "ничего не приходит в голову",
    "ничего не могу придумать",
    "ничего не могу вспомнить",
    "пока не придумала",
    "пока не придумал",
    "пока нечего сказать",
    "пока нечего написать",
    "не о чем писать",
    "не о чем рассказать",
]

SEVERE_SAD_PATTERNS = [
    "не хочу жить",
    "не хочу больше жить",
    "нет смысла жить",
    "не вижу смысла",
    "жизнь бессмысленна",
    "ненавижу свою жизнь",
    "хочу умереть",
    "никому не нужна",
    "никому не нужен",
    "никого нет рядом",
    "никто меня не любит",
    "я ничтожество",
    "я никчемная",
    "я никчемный",
    "ненавижу себя",
    "ненавижу все",
    "лучше бы меня не было",
]

GREETING_PATTERNS = [
    "привет",
    "привет!",
    "приветики",
    "приветик",
    "прив",
    "хай",
    "хай!",
    "ку",
    "здравствуйте",
    "добрый день",
    "добрый вечер",
    "доброе утро",
]

GREETING_RESPONSES = [
    "Привет 🙂 Расскажи, что сегодня было приятного.",
    "Привет. Давай вспомним, что немного порадовало тебя сегодня.",
    "Привет, я на связи. Что хорошего было в этом дне?",
    "Рада тебя видеть здесь. Что сегодня добавило хоть каплю тепла?",
    "Привет. Если хочешь, можешь написать одну маленькую радость за сегодня.",
]

JOY_EMOJIS = ["✨", "😊", "🌈", "💛", "🌟"]
REMINDER_EMOJIS = ["✨", "📌", "😊"]
STATS_EMOJIS = ["📊", "📈", "⭐"]
ACHIEVEMENT_EMOJIS = ["🏅", "🎉", "🌟"]
CALM_EMOJIS = ["🙂", "🌿", "✨", "☕", "🕊", "🍃"]

SAD_RESPONSES = [
    "Звучит как непростой день. Это нормально — не вытаскивать из него радость силой.\n\n"
    "Попробуй вспомнить одну маленькую вещь, которая была не совсем ужасной: тёплый чай, музыка, сообщение от кого-то. "
    "Если захочешь, можешь написать мне об этом.",
    "Понимаю, что сегодня могло быть тяжело.\n\n"
    "Не обязательно искать что-то большое. Иногда достаточно момента, когда стало чуть-чуть легче. "
    "Если найдёшь такую деталь — напиши, я сохраню её для тебя.",
    "Кажется, день выжал много сил.\n\n"
    "Если получится, вспомни хоть один нейтральный или слегка тёплый момент. "
    "Это может быть что угодно — дорога домой, еда, короткий отдых. Можно написать мне об этом.",
    "Бывает, что день совсем не радует. Так тоже можно.\n\n"
    "Если будет желание, попробуй отметить хотя бы одну маленькую опору: что-то, что помогло дойти до вечера. "
    "Я аккуратно сохраню это как тихую радость дня.",
    "Слышу, что сегодня тяжело.\n\n"
    "Иногда единственное хорошее — то, что день закончился. И это тоже результат. "
    "Если захочешь, напиши одну небольшую деталь, которая была чуть мягче, чем всё остальное.",
]

TIRED_RESPONSES = [
    "Похоже, сегодня было непросто, и ты сильно устала.\n\n"
    "Это не про слабость, а про то, что ты много на себе несёшь. "
    "Если получится, вспомни одну маленькую вещь, которая помогла дотянуть этот день.",
    "Слышу усталость. И это понятно.\n\n"
    "Можно не быть продуктивной каждый день. "
    "Если захочешь, напиши, что сегодня было хоть немного приятным или дающим передышку.",
    "Звучит так, будто энергии почти не осталось.\n\n"
    "Иногда радость — это несколько минут тишины, еда или возможность просто лечь. "
    "Если такая пауза была, можешь рассказать о ней.",
    "День точно забрал много сил.\n\n"
    "Попробуй отметить для себя хоть одну маленькую вещь, которая поддержала тебя сегодня. "
    "Если хочешь, напиши её, я сохраню.",
    "Очень похоже на состояние «батарейка на нуле».\n\n"
    "Ты всё равно дошла до этого момента, и это уже немало. "
    "Если вспомнится что-то чуть более мягкое в этом дне, можно написать мне об этом.",
]

ANXIETY_RESPONSES = [
    "Чувствуется тревога. Это не про слабость — скорее про важность того, что с тобой происходит.\n\n"
    "Если получится, напиши одну вещь, которая у тебя сегодня всё-таки вышла, пусть даже маленькая.",
    "Слышу, что внутри неспокойно.\n\n"
    "Иногда помогает вспомнить момент, когда тревога была чуть тише: сообщение, музыка, тёплый чай. "
    "Если захочешь, можешь рассказать об этом.",
    "Похоже, сегодня было много переживаний.\n\n"
    "Ты уже справлялась с разными ситуациями раньше. "
    "Если хочешь, напиши о моменте, где ты всё-таки справилась, несмотря на страх.",
    "Тревога умеет накручивать мысли.\n\n"
    "Давай немного приземлимся: что сегодня помогло не развалиться окончательно? "
    "Если вспомнишь — напиши, я запомню это для тебя.",
    "Я слышу твоё волнение.\n\n"
    "Не нужно быть спокойной на 100%. Если хочешь, можешь просто описать один небольшой эпизод дня, "
    "где было чуть менее тревожно. Я аккуратно сохраню его.",
]

JOY_RESPONSES = [
    "Записала это как твою радость дня.",
    "Сохранила. Такой момент точно стоит помнить.",
    "Добавила в твой дневник хорошего.",
    "Отметила эту радость. Спасибо, что поделилась.",
    "Записала. Пусть это будет твоей маленькой опорой.",
]

NO_JOY_RESPONSES = [
    "Иногда правда сложно сразу вспомнить что-то приятное. Если позже всплывёт маленький тёплый момент — просто напиши мне о нём.",
    "Окей, ничего страшного. Можно вернуться к радостям позже, когда что-то откликнется.",
    "Бывает, что в голове пусто — это нормально. Если днём появится хоть крошечный хороший момент, я буду здесь, чтобы его сохранить.",
]

SAD_RITUAL_DAYS = 3
SAD_RITUAL_THRESHOLD = 3

# Темы радостей для персонализации
THEME_KEYWORDS: Dict[str, List[str]] = {
    "еда": [
        "кофе", "чай", "какао", "печень", "печенье", "пицца", "торт", "тортик",
        "десерт", "шоколад", "конфет", "конфета", "шоколадка", "обед", "ужин",
        "завтрак", "обедала", "обедал", "ужинала", "ужинал", "завтракала",
        "завтракал", "кафе", "рестора", "булоч", "круассан", "вкусно", "фрукты",
        "ягоды", "суши", "роллы", "салат", "еда", "поесть",
    ],
    "люди": [
        "подруга", "подружка", "подруги", "друг", "друзья", "коллег", "мама",
        "папа", "родител", "семья", "брат", "сестра", "бабушка", "дедушка",
        "парень", "муж", "любимый", "любимая", "встретил", "встретила",
        "созвон", "звонок", "переписка", "чат", "компания", "вместе", "обнял",
        "обняла", "обнялись", "объятия",
    ],
    "природа": [
        "прогулка", "гуляла", "гулял", "парк", "лес", "река", "озеро", "море",
        "воздух", "свежий воздух", "солнце", "солнечно", "тёплая погода",
        "теплая погода", "снег", "дождь", "лист", "листья", "трава", "цветы",
        "цветок", "небо", "рассвет", "закат",
    ],
    "отдых": [
        "отдых", "отдохнула", "отдохнул", "полежала", "полежал", "ничего не делала",
        "ничего не делал", "выспалась", "выспался", "сон", "спала", "спал",
        "релакс", "расслабилась", "расслабился", "ванна", "маска для лица",
        "спа", "тишина", "покой", "паузу", "передышка",
    ],
    "успехи": [
        "сделала", "сделал", "успела", "успел", "закончила", "закончил",
        "сдала", "сдал", "получилось", "справилась", "справился", "доделала",
        "доделал", "выполнила", "выполнил", "отчиталась", "отчитался",
        "похвалили", "похвала", "результат", "достигла", "достиг", "прогресс",
        "шаг вперёд", "шаг вперед",
    ],
}

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
    # радости
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
    # тяжёлые/грустные/тревожные события
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sad_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    # состояние диалога (микро-диалоги, письмо себе и т.п.)
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
    # письма в будущее
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


def get_sad_count_last_days(chat_id: int, days: int) -> int:
    today_local = datetime.now().date()
    start = today_local - timedelta(days=days - 1)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM sad_events
        WHERE chat_id = ?
          AND substr(created_at,1,10) >= ?
        """,
        (chat_id, start.isoformat()),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_joys_for_week(chat_id: int, week_start: date) -> List[Tuple[str, str]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    start_str = week_start.isoformat()
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


def get_joys_for_date(chat_id: int, date_obj: date) -> List[Tuple[str, str]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    date_str = date_obj.isoformat()
    cur.execute(
        """
        SELECT created_at, text
        FROM joys
        WHERE chat_id = ?
          AND substr(created_at,1,10) = ?
        ORDER BY created_at ASC
        """,
        (chat_id, date_str),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_joys_between(chat_id: int, start_date: date, end_date: date) -> List[Tuple[str, str]]:
    """
    Радости за период [start_date; end_date].
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()
    cur.execute(
        """
        SELECT created_at, text
        FROM joys
        WHERE chat_id = ?
          AND substr(created_at,1,10) >= ?
          AND substr(created_at,1,10) <= ?
        ORDER BY created_at ASC
        """,
        (chat_id, start_str, end_str),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


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


def get_distinct_joy_dates(chat_id: int) -> List[date]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT substr(created_at, 1, 10) as d
        FROM joys
        WHERE chat_id = ?
        ORDER BY d ASC
        """,
        (chat_id,),
    )
    rows = cur.fetchall()
    conn.close()
    dates = []
    for (d_str,) in rows:
        try:
            dates.append(date.fromisoformat(d_str))
        except Exception:
            pass
    return dates


def get_first_joy_date(chat_id: int) -> Optional[date]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT MIN(substr(created_at, 1, 10))
        FROM joys
        WHERE chat_id = ?
        """,
        (chat_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return date.fromisoformat(row[0])
        except Exception:
            return None
    return None


def get_joys_last_n_days(chat_id: int, days: int = 7) -> int:
    today_local = datetime.now().date()
    start = today_local - timedelta(days=days - 1)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM joys
        WHERE chat_id = ?
          AND substr(created_at,1,10) >= ?
        """,
        (chat_id, start.isoformat()),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_current_streak(chat_id: int) -> int:
    dates = get_distinct_joy_dates(chat_id)
    if not dates:
        return 0

    today_local = datetime.now().date()
    last_date = dates[-1]
    if last_date < today_local - timedelta(days=1):
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


# --- dialog_state helpers ---

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


# --- future letters helpers ---

def add_future_letter(chat_id: int, text: str, days_ahead: int):
    now = datetime.now()
    send_at = now + timedelta(days=days_ahead)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO future_letters (chat_id, text, send_at, created_at, sent)
        VALUES (?, ?, ?, ?, 0)
        """,
        (
            chat_id,
            text,
            send_at.isoformat(timespec="seconds"),
            now.isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()


def get_due_letters() -> List[Tuple[int, int, str, str, str]]:
    """
    Возвращает письма, которые пора отправить:
    (id, chat_id, text, send_at, created_at)
    """
    now_iso = datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, chat_id, text, send_at, created_at
        FROM future_letters
        WHERE sent = 0
          AND send_at <= ?
        """,
        (now_iso,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def mark_letter_sent(letter_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE future_letters SET sent = 1 WHERE id = ?",
        (letter_id,),
    )
    conn.commit()
    conn.close()


# --------------------------
# Очистка текста
# --------------------------

def clean_profanity(text: str) -> str:
    lower = text.lower()
    for bad in BAD_WORDS:
        if bad in lower:
            replacement = "*" * len(bad)
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
            data={"text": text, "language": "ru"},
            timeout=10,
        )
        data = resp.json()
        matches = data.get("matches", [])
        if not matches:
            return text
        text_chars = list(text)
        for m in reversed(matches):
            repls = m.get("replacements")
            if not repls:
                continue
            best = repls[0].get("value")
            offset = m.get("offset", 0)
            length = m.get("length", 0)
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


def normalize_text_for_match(text: str) -> str:
    """
    Нормализация текста для сопоставления с паттернами:
    - нижний регистр
    - ё -> е
    - удаляем знаки препинания и эмодзи
    - сжимаем пробелы
    """
    lower = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^\w\s]+", " ", lower)
    normalized = " ".join(normalized.split())
    return normalized


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


def is_greeting_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    return any(lower == p for p in GREETING_PATTERNS)


def is_no_joy_message(text: str) -> bool:
    """
    Нейтральные фразы "не знаю, что написать" — не считаем радостью.
    Работает и без пробелов/смайлов.
    """
    lower = normalize_text_for_match(text)
    return any(p in lower for p in NO_JOY_PATTERNS)


# --------------------------
# Темы радостей (персонализация)
# --------------------------

def classify_joy_themes(text: str) -> List[str]:
    """
    Возвращает список тем (еда, люди, природа, отдых, успехи),
    к которым можно отнести эту радость.
    """
    result = []
    norm = normalize_text_for_match(text)
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in norm:
                result.append(theme)
                break
    return result


def summarize_themes(theme_counts: Dict[str, int]) -> Optional[str]:
    """
    Из словаря {тема: количество} делает человеческую фразу.
    Например: "чаще всего тебя радовали еда, люди и отдых".
    """
    filtered = {k: v for k, v in theme_counts.items() if v > 0}
    if not filtered:
        return None

    sorted_themes = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
    names = [t[0] for t in sorted_themes[:3]]

    if len(names) == 1:
        return f"чаще всего тебя радовала {names[0]}."
    elif len(names) == 2:
        return f"чаще всего тебя радовали {names[0]} и {names[1]}."
    else:
        return f"чаще всего тебя радовали {names[0]}, {names[1]} и {names[2]}."


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


def get_joy_response() -> str:
    return add_emoji_prefix(random.choice(JOY_RESPONSES))


def get_no_joy_response() -> str:
    return add_emoji_prefix(random.choice(NO_JOY_RESPONSES))


# --------------------------
# Ачивки (мягкие формулировки)
# --------------------------

def check_and_send_achievements(chat_id: int):
    total = get_joy_count(chat_id)
    streak = get_current_streak(chat_id)

    messages = []

    if total == 1:
        options = [
            "Ты сделала первый шаг — отметила свою первую радость. Это уже забота о себе.",
            "Первая радость записана. Хорошее, тихое начало.",
            "Первая запись есть. Дальше можно двигаться маленькими шагами.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif total == 7:
        options = [
            "У тебя уже сложилась целая неделя с отмеченными радостями. Красивая привычка.",
            "Похоже, ты уже привыкла замечать хорошее в течение недели.",
            "Ты регулярно возвращаешься сюда и отмечаешь светлые моменты — это ценно.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif total == 30:
        options = [
            "У тебя уже много зафиксированных приятных моментов. Это целая личная история.",
            "Собралось заметно много радостей — они уже не теряются в памяти.",
            "Ты оставила довольно длинный след из хороших моментов за собой.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))

    if streak == 3:
        options = [
            "Несколько дней подряд ты находишь что-то хорошее. Это очень бережно к себе.",
            "Ты несколько дней подряд отмечаешь радости — это уже стабильность.",
            "Похоже, у тебя появляется привычка замечать приятное даже в обычных днях.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif streak == 7:
        options = [
            "На протяжении недели ты каждый день находила для себя что-то поддерживающее.",
            "Ты держишь ритм, находя что-то хорошее каждый день — это вдохновляет.",
            "Неделя подряд с радостями — очень тёплый результат.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif streak == 30:
        options = [
            "Ты продолжаешь замечать хорошее изо дня в день. Это серьёзная внутренняя работа.",
            "Кажется, радости стали естественной частью твоего дня.",
            "То, что ты столько времени не бросаешь этот дневник, говорит о большой заботе о себе.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))

    for m in messages:
        send_message(chat_id, m)


# --------------------------
# Ритуал «3 маленькие радости»
# --------------------------

def maybe_offer_ritual(chat_id: int):
    sad_count = get_sad_count_last_days(chat_id, SAD_RITUAL_DAYS)
    if sad_count >= SAD_RITUAL_THRESHOLD:
        send_message(
            chat_id,
            add_emoji_prefix(
                "Вижу, что последние дни даются непросто.\n\n"
                "Можно попробовать небольшой ритуал: сегодня перед сном отметь для себя три маленькие радости.\n"
                "Не обязательно что-то большое — еда, уют, спокойный момент. "
                "Если захочешь, можешь написать их мне."
            ),
        )


# --------------------------
# Недельный и месячный обзоры
# --------------------------

def send_weekly_human_summary(chat_id: int):
    """
    Воскресный обзор за 7 дней:
    - основные темы радостей
    - мягкая формулировка
    """
    today_local = datetime.now().date()
    start = today_local - timedelta(days=6)
    joys = get_joys_between(chat_id, start, today_local)

    if not joys:
        send_message(
            chat_id,
            add_emoji_prefix(
                "На этой неделе у меня почти нет твоих радостей.\n"
                "Если дашь себе шанс, в следующую неделю можно попробовать находить хотя бы одну маленькую опору в день."
            )
        )
        return

    theme_counts: Dict[str, int] = {k: 0 for k in THEME_KEYWORDS.keys()}
    for _, text in joys:
        themes = classify_joy_themes(text)
        for t in themes:
            theme_counts[t] += 1

    themes_phrase = summarize_themes(theme_counts)

    lines = []
    for created_at, text in joys:
        try:
            dt = datetime.fromisoformat(created_at)
            date_str = dt.strftime("%d.%m")
        except Exception:
            date_str = created_at[:10]
        emo = random.choice(JOY_EMOJIS)
        lines.append(f"{emo} {date_str} — {text}")

    header = "Немного хорошего, которое было с тобой на этой неделе:"
    body = "\n".join(lines)

    if themes_phrase:
        extra = f"\n\nЕсли коротко, на этой неделе {themes_phrase}"
    else:
        extra = ""

    send_message(chat_id, f"{header}\n\n{body}{extra}")


def send_monthly_human_summary(chat_id: int):
    """
    Обзор за прошлый месяц:
    - общее ощущение
    - основные темы
    """
    today_local = datetime.now().date()
    first_this_month = today_local.replace(day=1)
    # предыдущий месяц
    end_prev = first_this_month - timedelta(days=1)
    start_prev = end_prev.replace(day=1)

    joys = get_joys_between(chat_id, start_prev, end_prev)
    if not joys:
        send_message(
            chat_id,
            add_emoji_prefix(
                "За прошлый месяц у меня почти нет твоих записей.\n"
                "Если захочешь, этот месяц может стать началом более тёплой и внимательной истории с собой."
            )
        )
        return

    theme_counts: Dict[str, int] = {k: 0 for k in THEME_KEYWORDS.keys()}
    for _, text in joys:
        themes = classify_joy_themes(text)
        for t in themes:
            theme_counts[t] += 1

    themes_phrase = summarize_themes(theme_counts)
    total = len(joys)

    month_name = start_prev.strftime("%B")
    month_name_ru = {
        "January": "январь", "February": "февраль", "March": "март",
        "April": "апрель", "May": "май", "June": "июнь",
        "July": "июль", "August": "август", "September": "сентябрь",
        "October": "октябрь", "November": "ноябрь", "December": "декабрь",
    }.get(month_name, month_name)

    header = f"Небольшой взгляд назад: твой {month_name_ru}."
    if themes_phrase:
        intro = (
            f"{header}\n\n"
            f"За этот месяц ты сохранила для себя довольно много тёплых моментов. "
            f"Если собрать их вместе, видно, что {themes_phrase}"
        )
    else:
        intro = (
            f"{header}\n\n"
            "За этот месяц у тебя накопилось немало небольших радостей. "
            "Они могли быть очень разными, но все они — о тебе и для тебя."
        )

    send_message(chat_id, add_emoji_prefix(intro))


# --------------------------
# Статистика
# --------------------------

def send_stats(chat_id: int):
    total = get_joy_count(chat_id)
    last7 = get_joys_last_n_days(chat_id, 7)
    streak = get_current_streak(chat_id)
    first_date = get_first_joy_date(chat_id)

    em = random.choice(STATS_EMOJIS)

    if total == 0:
        send_message(
            chat_id,
            f"{em} Пока у тебя нет записанных радостей.\n"
            "Можно начать с одной небольшой, когда почувствуешь ресурс."
        )
        return

    first_str = first_date.strftime("%d.%m.%Y") if first_date else "—"

    msg = (
        f"{em} Небольшая статистика:\n\n"
        f"• У тебя уже есть заметное количество сохранённых радостей.\n"
        f"• За последние 7 дней ты всё равно находила что-то хорошее, даже если дни были разными.\n"
        f"• Сейчас у тебя есть серия дней, где ты не забываешь про себя.\n"
        f"• Первая запись появилась: {first_str}.\n\n"
        "Каждая маленькая радость — это шаг в сторону бережного отношения к себе."
    )
    send_message(chat_id, msg)


# --------------------------
# Письмо себе в будущее
# --------------------------

def handle_letter_command(chat_id: int):
    """
    /letter — спрашиваем, на какой срок отправить письмо.
    """
    clear_dialog_state(chat_id)
    send_message(
        chat_id,
        add_emoji_prefix(
            "Хочешь написать письмо себе в будущее.\n\n"
            "Выбери срок, через который я тебе его пришлю:\n"
            "• 7 — через неделю\n"
            "• 14 — через две недели\n"
            "• 30 — через месяц\n\n"
            "Просто напиши цифру: 7, 14 или 30."
        )
    )
    set_dialog_state(chat_id, "await_letter_period", None)


def handle_letter_period(chat_id: int, text: str):
    norm = normalize_text_for_match(text)
    if norm not in ["7", "14", "30"]:
        send_message(
            chat_id,
            add_emoji_prefix(
                "Не совсем поняла срок.\n"
                "Напиши, пожалуйста, только цифру: 7, 14 или 30."
            )
        )
        return
    days = int(norm)
    set_dialog_state(chat_id, "await_letter_text", {"days": days})
    send_message(
        chat_id,
        add_emoji_prefix(
            "Хорошо. Напиши сейчас письмо себе — той, которая будет читать его через этот срок.\n\n"
            "Можно рассказать, как ты себя чувствуешь сейчас, что тебе важно, о чём мечтаешь или что хочешь себе напомнить."
        )
    )


def handle_letter_text(chat_id: int, text: str, meta: dict):
    days = meta.get("days", 7)
    cleaned = text.strip()
    if not cleaned:
        send_message(
            chat_id,
            add_emoji_prefix(
                "Похоже, письмо получилось пустым.\n"
                "Попробуй написать хотя бы пару строк для себя из будущего."
            )
        )
        return

    add_future_letter(chat_id, cleaned, days)
    clear_dialog_state(chat_id)

    target_date = (datetime.now() + timedelta(days=days)).strftime("%d.%m.%Y")
    send_message(
        chat_id,
        add_emoji_prefix(
            f"Я сохраню это письмо и пришлю его тебе примерно {target_date}.\n"
            "Когда получишь его, это будет небольшая встреча с собой из прошлого."
        )
    )


# --------------------------
# Микродиалоги (маленькая опора)
# --------------------------

def start_small_joy_dialog(chat_id: int):
    """
    После грусти/тревоги/усталости предлагаем найти одну маленькую опору.
    """
    send_message(
        chat_id,
        add_emoji_prefix(
            "Если захочешь, можем попробовать найти одну маленькую опору в этом дне.\n"
            "Напиши о моменте, который был хотя бы чуть-чуть мягче остальных."
        )
    )
    set_dialog_state(chat_id, "await_small_joy", None)


def handle_small_joy_reply(chat_id: int, text: str):
    cleaned = clean_text_pipeline(text)
    if not cleaned:
        send_message(
            chat_id,
            add_emoji_prefix(
                "Мне не удалось ничего сохранить.\n"
                "Попробуй описать хотя бы маленький момент: еду, паузу, сообщение, взгляд, музыку."
            )
        )
        return
    add_joy(chat_id, cleaned)
    clear_dialog_state(chat_id)
    send_message(
        chat_id,
        add_emoji_prefix(
            "Спасибо, что всё-таки нашла маленькую опору в этом дне. Я её аккуратно сохранила."
        )
    )
    check_and_send_achievements(chat_id)


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

    # Команды, которые всегда можно вызвать
    if stripped.startswith("/start"):
        clear_dialog_state(chat_id)
        send_message(
            chat_id,
            "Привет. Я помогу тебе замечать и сохранять маленькие радости.\n\n"
            "Каждый день можно писать сюда что-то приятное из дня: встречу, вкусный кофе, спокойный вечер.\n"
            "В 19:00 я напомню, если ты ничего не написала, а в 22:00 пришлю небольшой отчёт за день.\n\n"
            "Если захочешь, можешь ещё написать себе письмо в будущее командой /letter."
        )
        return

    if stripped.startswith("/stats"):
        send_stats(chat_id)
        return

    if stripped.startswith("/letter"):
        handle_letter_command(chat_id)
        return

    # Сначала смотрим состояние диалога
    state, meta = get_dialog_state(chat_id)

    # Если ждём маленькую опору
    if state == "await_small_joy":
        handle_small_joy_reply(chat_id, text)
        return

    # Если ждём выбор срока письма
    if state == "await_letter_period":
        handle_letter_period(chat_id, text)
        return

    # Если ждём текст письма
    if state == "await_letter_text":
        handle_letter_text(chat_id, text, meta or {})
        return

    # Дальше — обычная логика
    cleaned = clean_text_pipeline(text)
    if not cleaned:
        send_message(
            chat_id,
            "Мне не удалось ничего сохранить.\n"
            "Попробуй написать чуть конкретнее, что тебя сегодня порадовало."
        )
        return

    # Приветствие — отвечаем, но НЕ записываем как радость
    if is_greeting_message(cleaned):
        send_message(chat_id, get_greeting_response())
        return

    # очень тяжёлые сообщения
    if is_severe_sad_message(cleaned):
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
        maybe_offer_ritual(chat_id)
        # здесь без микродиалога, чтобы не давить
        return

    # тревога
    if is_anxiety_message(cleaned):
        send_message(chat_id, get_anxiety_response())
        add_sad_event(chat_id)
        maybe_offer_ritual(chat_id)
        start_small_joy_dialog(chat_id)
        return

    # усталость
    if is_tired_message(cleaned):
        send_message(chat_id, get_tired_response())
        add_sad_event(chat_id)
        maybe_offer_ritual(chat_id)
        start_small_joy_dialog(chat_id)
        return

    # грусть / «ничего хорошего»
    if is_sad_message(cleaned):
        send_message(chat_id, get_sad_response())
        add_sad_event(chat_id)
        maybe_offer_ritual(chat_id)
        start_small_joy_dialog(chat_id)
        return

    # нейтральные фразы "не знаю, что написать" — не записываем как радость
    if is_no_joy_message(cleaned):
        send_message(chat_id, get_no_joy_response())
        return

    # Обычная радость
    add_joy(chat_id, cleaned)
    send_message(chat_id, get_joy_response())
    check_and_send_achievements(chat_id)


# --------------------------
# Еженедельный и месячный раннеры
# --------------------------

def weekly_summary_runner():
    """
    Воскресенье 22:15 — недельный обзор.
    """
    print("Weekly summary runner started.")
    sent_weeks = set()

    while True:
        now = datetime.now()
        today = now.date()
        year, week_num, _ = today.isocalendar()
        key = (year, week_num)

        # очищаем старые ключи
        for k in list(sent_weeks):
            if k[0] != year or k[1] != week_num:
                sent_weeks.remove(k)

        if now.isoweekday() == 7 and now.hour == 22 and now.minute == 15:
            if key not in sent_weeks:
                print("Sending weekly human summaries...")
                for user_id in get_all_user_ids():
                    try:
                        send_weekly_human_summary(user_id)
                    except Exception as e:
                        print(f"Error sending weekly summary to {user_id}:", e)
                sent_weeks.add(key)

        time.sleep(60)


def monthly_summary_runner():
    """
    1-е число месяца 20:00 — обзор за прошлый месяц.
    """
    print("Monthly summary runner started.")
    sent_months = set()  # (year, month)

    while True:
        now = datetime.now()
        today = now.date()
        ym = (today.year, today.month)

        for k in list(sent_months):
            if k != ym:
                sent_months.remove(k)

        if today.day == 1 and now.hour == 20 and now.minute == 0:
            if ym not in sent_months:
                print("Sending monthly human summaries...")
                for user_id in get_all_user_ids():
                    try:
                        send_monthly_human_summary(user_id)
                    except Exception as e:
                        print(f"Error sending monthly summary to {user_id}:", e)
                sent_months.add(ym)

        time.sleep(60)


# --------------------------
# Ежедневные напоминания (19:00)
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

        if now.hour == 19 and now.minute == 0:
            if today not in reminded_dates:
                print("Sending daily reminders...")
                for user_id in get_all_user_ids():
                    try:
                        if not has_joy_for_date(user_id, today):
                            emo = random.choice(REMINDER_EMOJIS)
                            send_message(
                                user_id,
                                f"{emo} Уже 19:00.\n"
                                "Если сегодня было хоть что-то немного приятное, можешь написать мне об этом."
                            )
                    except Exception as e:
                        print(f"Error sending daily reminder to {user_id}:", e)
                reminded_dates.add(today)

        time.sleep(60)


# --------------------------
# Ежедневный отчёт (22:00)
# --------------------------

def daily_report_runner():
    print("Daily report runner started.")
    reported_dates = set()

    while True:
        now = datetime.now()
        today = now.date()

        for d in list(reported_dates):
            if d != today:
                reported_dates.remove(d)

        if now.hour == 22 and now.minute == 0:
            if today not in reported_dates:
                print("Sending daily reports...")
                for user_id in get_all_user_ids():
                    try:
                        send_daily_report_for_user(user_id)
                    except Exception as e:
                        print(f"Error sending daily report to {user_id}:", e)
                reported_dates.add(today)

        time.sleep(60)


# --------------------------
# Раннер писем в будущее
# --------------------------

def future_letters_runner():
    print("Future letters runner started.")
    while True:
        try:
            letters = get_due_letters()
            if letters:
                print(f"Sending {len(letters)} future letters...")
            for letter_id, chat_id, text, send_at, created_at in letters:
                try:
                    # считаем разницу в днях
                    try:
                        dt_created = datetime.fromisoformat(created_at)
                        dt_send = datetime.fromisoformat(send_at)
                        days_diff = (dt_send.date() - dt_created.date()).days
                    except Exception:
                        days_diff = None

                    if days_diff and days_diff > 0:
                        intro = (
                            "Сегодня у тебя небольшая встреча с собой из прошлого.\n\n"
                            f"Это письмо ты написала примерно {days_diff} дней назад:"
                        )
                    else:
                        intro = (
                            "Сегодня у тебя небольшая встреча с собой из прошлого.\n\n"
                            "Вот письмо, которое ты написала раньше:"
                        )

                    full = f"{add_emoji_prefix(intro)}\n\n{text}"
                    send_message(chat_id, full)
                    mark_letter_sent(letter_id)
                except Exception as e:
                    print(f"Error sending future letter {letter_id}:", e)
        except Exception as e:
            print("future_letters_runner error:", e)

        time.sleep(60)


# --------------------------
# Ежедневный отчёт за день (уже определён выше)
# --------------------------

def send_daily_report_for_user(chat_id: int):
    today_local = datetime.now().date()
    joys = get_joys_for_date(chat_id, today_local)

    if not joys:
        send_message(
            chat_id,
            add_emoji_prefix(
                "Сегодня у меня нет сохранённых радостей.\n"
                "Если день был тяжёлым — так тоже бывает. Завтра можно попробовать снова."
            )
        )
        return

    lines = []
    for created_at, text in joys:
        try:
            dt = datetime.fromisoformat(created_at)
            time_str = dt.strftime("%H:%M")
        except Exception:
            time_str = created_at[11:16]
        emo = random.choice(JOY_EMOJIS)
        lines.append(f"{emo} {time_str} — {text}")

    header = "Вот что хорошего ты отметила сегодня:"
    body = "\n".join(lines)
    send_message(chat_id, f"{header}\n\n{body}")


# --------------------------
# main
# --------------------------

def main():
    init_db()

    t_daily_reminder = threading.Thread(target=daily_reminder_runner, daemon=True)
    t_daily_reminder.start()

    t_daily_report = threading.Thread(target=daily_report_runner, daemon=True)
    t_daily_report.start()

    t_weekly = threading.Thread(target=weekly_summary_runner, daemon=True)
    t_weekly.start()

    t_monthly = threading.Thread(target=monthly_summary_runner, daemon=True)
    t_monthly.start()

    t_letters = threading.Thread(target=future_letters_runner, daemon=True)
    t_letters.start()

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
