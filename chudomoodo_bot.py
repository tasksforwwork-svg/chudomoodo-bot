"""
chudomoodo_bot.py

Telegram-бот "Дневник маленьких радостей".

Что умеет:

- принимает от пользователя короткие тексты-радости;
- очищает мат и нецензурную лексику;
- сохраняет радости в SQLite;
- распознаёт базовые состояния: радость / грусть / усталость / тревогу / тяжёлые фразы;
- хранит эмоции сообщений и простые ключевые слова радостей (темы);
- ЕЖЕДНЕВНЫЙ РЕЖИМ:
    - в 19:00 — напоминание, если за день не было ни одной радости;
    - в 22:00 — отчёт с радостями за текущий день;
- защита от тоски: отдельные реакции на грусть, усталость, тревогу, тяжёлые фразы;
- спокойные тексты-ответы с одним эмодзи в начале;
- ачивки за количество радостей и стрики по дням;
- статистика по команде /stats:
    - сколько радостей всего, за 7 дней, стрик;
    - популярные темы радостей;
    - эмоции недели;
- /export — экспорт радостей за последние 30 дней;
- задел под "самообучение": бот собирает статистику эмоций и ключевых слов.
"""

import os
import time
import sqlite3
import threading
import random
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

USE_LANGTOOL = False  # оставляем возможность, но по умолчанию выключено
LANGTOOL_URL = "https://api.languagetool.org/v2/check"

# --------------------------
# Лексика и паттерны
# --------------------------

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
    "Привет. Расскажи, что сегодня было хоть немного приятным.",
    "Привет. Давай вспомним, что добавило тепла в этот день.",
    "Привет, я на связи. Что хорошего было в этом дне?",
    "Рада тебя видеть. Если хочешь, напиши одну маленькую радость.",
    "Привет. Можешь начать с самой простой вещи, которая тебя поддержала.",
]

JOY_EMOJIS = ["✨", "😊", "🌈", "💛", "🌟"]
REMINDER_EMOJIS = ["✨", "📌", "😊"]
STATS_EMOJIS = ["📊", "📈", "⭐"]
CALM_EMOJIS = ["🙂", "🌿", "✨", "☕", "🕊", "🍃"]

JOY_RESPONSES = [
    "Записала это как твою радость дня.",
    "Сохранила. Такой момент точно стоит помнить.",
    "Добавила в твой дневник хорошего.",
    "Отметила эту радость. Спасибо, что поделилась.",
    "Записала. Пусть это будет твоей маленькой опорой.",
]

SAD_RESPONSES = [
    "Звучит как непростой день. Не обязательно вытаскивать из него радость силой.\n\n"
    "Если захочешь, попробуй вспомнить один момент, который был чуть мягче остальных.",
    "Понимаю, что сегодня могло быть тяжело.\n\n"
    "Можно не искать чего-то большого. Иногда достаточно тёплого чая или сообщения от кого-то близкого.",
    "Бывает, что день совсем не радует. Так тоже можно.\n\n"
    "Если когда-нибудь захочешь, можешь отметить хотя бы одну небольшую опору — я её сохраню.",
]

TIRED_RESPONSES = [
    "Похоже, сегодня было непросто, и ты сильно устала.\n\n"
    "Это не про слабость, а про то, что ты много на себе несёшь.",
    "Слышу усталость. Не обязательно быть продуктивной каждый день.\n\n"
    "Если захочешь, напиши, что сегодня дало тебе хоть маленькую передышку.",
    "Энергии сегодня явно было мало.\n\n"
    "Иногда радость — это несколько минут тишины или возможность просто лечь и выдохнуть.",
]

ANXIETY_RESPONSES = [
    "Чувствуется тревога. Это значит, что для тебя многое важно.\n\n"
    "Попробуй вспомнить одну вещь, с которой ты всё-таки справилась сегодня.",
    "Слышу, что внутри неспокойно.\n\n"
    "Иногда помогает зацепиться за момент, когда тревога была чуть тише — музыка, разговор, чай.",
    "Тревога умеет накручивать. Но ты уже справлялась с разными ситуациями раньше.\n\n"
    "Если хочешь, можешь написать о моменте, где ты всё-таки выдержала этот день.",
]

# Стоп-слова для ключевых слов
STOPWORDS = {
    "и", "но", "а", "что", "это", "как", "когда", "я", "мы", "он", "она", "они",
    "в", "на", "над", "под", "про", "по", "за", "из", "у", "с", "со",
    "то", "же", "или", "так", "ещё", "еще", "бы", "ли", "тут", "там",
    "весь", "все", "всю", "мой", "моя", "мои", "твой", "твоя", "твои",
}

# Пороги для ритуала «3 маленькие радости»
SAD_RITUAL_DAYS = 3
SAD_RITUAL_THRESHOLD = 3

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
        CREATE TABLE IF NOT EXISTS message_emotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            emotion TEXT NOT NULL,
            source_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS joy_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
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


def add_message_emotion(chat_id: int, emotion: str, source_text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO message_emotions (chat_id, emotion, source_text, created_at) VALUES (?, ?, ?, ?)",
        (chat_id, emotion, source_text, created_at),
    )
    conn.commit()
    conn.close()


def add_joy_keywords(chat_id: int, keywords: List[str]):
    if not keywords:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    for kw in keywords:
        cur.execute(
            "INSERT INTO joy_keywords (chat_id, keyword, created_at) VALUES (?, ?, ?)",
            (chat_id, kw, created_at),
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


def get_top_keywords(chat_id: int, days: Optional[int] = None, limit: int = 3) -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if days is None:
        cur.execute(
            """
            SELECT keyword, COUNT(*) as c
            FROM joy_keywords
            WHERE chat_id = ?
            GROUP BY keyword
            ORDER BY c DESC
            LIMIT ?
            """,
            (chat_id, limit),
        )
    else:
        today_local = datetime.now().date()
        start = today_local - timedelta(days=days - 1)
        cur.execute(
            """
            SELECT keyword, COUNT(*) as c
            FROM joy_keywords
            WHERE chat_id = ?
              AND substr(created_at,1,10) >= ?
            GROUP BY keyword
            ORDER BY c DESC
            LIMIT ?
            """,
            (chat_id, start.isoformat(), limit),
        )

    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_emotion_stats_last_days(chat_id: int, days: int = 7) -> Dict[str, int]:
    today_local = datetime.now().date()
    start = today_local - timedelta(days=days - 1)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT emotion, COUNT(*)
        FROM message_emotions
        WHERE chat_id = ?
          AND substr(created_at,1,10) >= ?
        GROUP BY emotion
        """,
        (chat_id, start.isoformat()),
    )
    rows = cur.fetchall()
    conn.close()
    return {emotion: count for emotion, count in rows}


def get_joys_for_last_days(chat_id: int, days: int = 30) -> List[Tuple[str, str]]:
    today_local = datetime.now().date()
    start = today_local - timedelta(days=days - 1)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT created_at, text
        FROM joys
        WHERE chat_id = ?
          AND substr(created_at,1,10) >= ?
        ORDER BY created_at ASC
        """,
        (chat_id, start.isoformat()),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

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

# --------------------------
# Распознавание состояний
# --------------------------

def is_severe_sad_message(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in SEVERE_SAD_PATTERNS)


def is_sad_message(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in SAD_PATTERNS)


def is_tired_message(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in TIRED_PATTERNS)


def is_anxiety_message(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in ANXIETY_PATTERNS)


def is_greeting_message(text: str) -> bool:
    lower = text.lower().strip()
    return any(lower == p for p in GREETING_PATTERNS)


def analyze_emotion(text: str) -> str:
    """
    Простая разметка эмоций.
    Возвращает: 'severe_sad', 'sad', 'tired', 'anxiety', 'joy', 'other'.
    """
    if is_severe_sad_message(text):
        return "severe_sad"
    if is_anxiety_message(text):
        return "anxiety"
    if is_tired_message(text):
        return "tired"
    if is_sad_message(text):
        return "sad"
    # очень грубо: если не команда и не приветствие, считаем радостью
    if not text.startswith("/") and not is_greeting_message(text):
        return "joy"
    return "other"


def extract_keywords(text: str, max_kw: int = 5) -> List[str]:
    cleaned = ""
    for ch in text.lower():
        if ch.isalpha() or ch.isdigit() or ch == " ":
            cleaned += ch
        else:
            cleaned += " "
    words = [w for w in cleaned.split() if len(w) > 2 and w not in STOPWORDS]
    # простая уникализация порядка появления
    seen = set()
    result = []
    for w in words:
        if w not in seen:
            seen.add(w)
            result.append(w)
        if len(result) >= max_kw:
            break
    return result

# --------------------------
# Генерация текстов ответов
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

# --------------------------
# Ачивки
# --------------------------

def check_and_send_achievements(chat_id: int):
    total = get_joy_count(chat_id)
    streak = get_current_streak(chat_id)

    messages = []

    if total == 1:
        options = [
            "Первая радость записана. Хорошее начало.",
            "Ты сделала первый шаг. Дальше будет проще замечать приятное.",
            "Первая запись есть. Можно потихоньку продолжать.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif total == 7:
        options = [
            "Семь записанных радостей — уже целая неделя.",
            "Неделя с отмеченными радостями. Это хорошая привычка.",
            "У тебя уже семь радостей в копилке. Звучит здорово.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif total == 30:
        options = [
            "Тридцать радостей — солидная коллекция.",
            "30 записей — это уже заметный след в твоём ежедневии.",
            "У тебя 30 зафиксированных приятных моментов. Это важно.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))

    if streak == 3:
        options = [
            "Три дня подряд ты находишь что-то хорошее. Это очень ценно.",
            "Три дня подряд с радостями. Классный стрик.",
            "Ты уже три дня подряд уделяешь внимание хорошему.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif streak == 7:
        options = [
            "Неделя подряд с маленькими радостями. Красивая серия.",
            "Семь дней подряд ты что-то отмечаешь для себя. Это много.",
            "Неделя без пропусков — стабильная забота о себе.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif streak == 30:
        options = [
            "30 дней подряд — очень сильный результат.",
            "Месяц с ежедневными радостями. Это достойно уважения.",
            "Ты целый месяц находишь что-то хорошее каждый день.",
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
                "Можно попробовать небольшой ритуал: сегодня перед сном отметить для себя три маленькие радости. "
                "Не обязательно что-то большое — еда, уют, спокойный момент. "
                "Если захочешь, можешь написать их мне."
            ),
        )

# --------------------------
# Ежедневный отчёт за день (22:00)
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
# Статистика /stats
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

    top_all = get_top_keywords(chat_id, None, 3)
    top_week = get_top_keywords(chat_id, 7, 3)
    emo_stats = get_emotion_stats_last_days(chat_id, 7)

    lines = [
        f"{em} Небольшая сводка:",
        "",
        f"• Всего радостей: {total}",
        f"• За последние 7 дней: {last7}",
        f"• Текущий стрик по дням: {streak}",
        f"• Первая запись: {first_str}",
    ]

    if top_all:
        lines.append("")
        lines.append(
            "• Чаще всего в твоих радостях встречаются: " + ", ".join(top_all) + "."
        )

    if top_week:
        lines.append(
            "• За последние 7 дней ты чаще всего писала про: " + ", ".join(top_week) + "."
        )

    if emo_stats:
        parts = []
        mapping = {
            "joy": "радости",
            "sad": "грусть",
            "tired": "усталость",
            "anxiety": "тревогу",
            "severe_sad": "очень тяжёлые чувства",
        }
        for key, label in mapping.items():
            if key in emo_stats:
                parts.append(f"{label} — {emo_stats[key]}")
        if parts:
            lines.append("")
            lines.append("• Эмоции за последние 7 дней: " + ", ".join(parts) + ".")

    lines.append("")
    lines.append("Ты уже проделала заметную работу для себя.")

    send_message(chat_id, "\n".join(lines))

# --------------------------
# Экспорт /export
# --------------------------

def send_export(chat_id: int, days: int = 30):
    joys = get_joys_for_last_days(chat_id, days)
    if not joys:
        send_message(
            chat_id,
            add_emoji_prefix(
                "За этот период у меня нет сохранённых радостей.\n"
                "Можно начать отмечать их уже сегодня."
            )
        )
        return

    header = f"Твои радости за последние {days} дней:"
    lines = [header, ""]
    for created_at, text in joys:
        try:
            dt = datetime.fromisoformat(created_at)
            date_str = dt.strftime("%d.%m %H:%M")
        except Exception:
            date_str = created_at[:16]
        emo = random.choice(JOY_EMOJIS)
        lines.append(f"{emo} {date_str} — {text}")

    full_text = "\n".join(lines)

    # Телеграм ограничен по длине сообщения, разобьём при необходимости
    max_len = 3500
    if len(full_text) <= max_len:
        send_message(chat_id, full_text)
    else:
        chunk = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > max_len:
                send_message(chat_id, "\n".join(chunk))
                chunk = []
                current_len = 0
            chunk.append(line)
            current_len += len(line) + 1
        if chunk:
            send_message(chat_id, "\n".join(chunk))

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

    # /start
    if stripped.startswith("/start"):
        send_message(
            chat_id,
            "Привет. Я помогу тебе замечать и сохранять маленькие радости.\n\n"
            "Каждый день можно писать сюда что-то приятное из дня: встречу, вкусный кофе, спокойный вечер.\n"
            "В 19:00 я напомню, если ты ничего не написала, а в 22:00 пришлю небольшой отчёт за день.\n\n"
            "Команды:\n"
            "• /stats — небольшая статистика по радостям и эмоциям.\n"
            "• /export — твои радости за последние 30 дней."
        )
        return

    # /stats
    if stripped.startswith("/stats"):
        send_stats(chat_id)
        return

    # /export (пока без параметров)
    if stripped.startswith("/export"):
        send_export(chat_id, 30)
        return

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
        add_message_emotion(chat_id, "other", cleaned)
        return

    emotion = analyze_emotion(cleaned)

    # очень тяжёлые сообщения
    if emotion == "severe_sad":
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
        add_message_emotion(chat_id, "severe_sad", cleaned)
        maybe_offer_ritual(chat_id)
        return

    # тревога
    if emotion == "anxiety":
        send_message(chat_id, get_anxiety_response())
        add_sad_event(chat_id)
        add_message_emotion(chat_id, "anxiety", cleaned)
        maybe_offer_ritual(chat_id)
        return

    # усталость
    if emotion == "tired":
        send_message(chat_id, get_tired_response())
        add_sad_event(chat_id)
        add_message_emotion(chat_id, "tired", cleaned)
        maybe_offer_ritual(chat_id)
        return

    # грусть / «ничего хорошего»
    if emotion == "sad":
        send_message(chat_id, get_sad_response())
        add_sad_event(chat_id)
        add_message_emotion(chat_id, "sad", cleaned)
        maybe_offer_ritual(chat_id)
        return

    # обычная радость (по умолчанию)
    add_joy(chat_id, cleaned)
    add_message_emotion(chat_id, "joy", cleaned)
    keywords = extract_keywords(cleaned)
    add_joy_keywords(chat_id, keywords)
    send_message(chat_id, get_joy_response())
    check_and_send_achievements(chat_id)

# --------------------------
# Ежедневные напоминания в 19:00
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
# Ежедневный отчёт в 22:00
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
# Главный цикл бота
# --------------------------

def main():
    init_db()

    t_daily_reminder = threading.Thread(target=daily_reminder_runner, daemon=True)
    t_daily_reminder.start()

    t_daily_report = threading.Thread(target=daily_report_runner, daemon=True)
    t_daily_report.start()

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
