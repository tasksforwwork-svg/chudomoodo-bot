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
- ачивки за количество радостей и стрики по дням;
- статистика по команде /stats;
- если часто грустно / тревожно / тяжело, предлагает мини-ритуал: 3 маленькие радости за день.
- ДОПОЛНЕНО:
    - сохраняет эмоцию каждого сообщения в таблицу message_emotions;
    - извлекает ключевые слова радостей и сохраняет их в joy_keywords.
"""

import os
import time
import sqlite3
import threading
import random
import re
from datetime import datetime, timedelta, date
from typing import List, Tuple, Optional

import requests

# --------------------------
# CONFIG
# --------------------------

# Вставляем токен напрямую, чтобы не зависеть от переменных окружения на хостинге
TOKEN = "8485558912:AAGMxJcqks9l7RoxK4U3NVcdtTnw6mdg1WQ"

API_URL = f"https://api.telegram.org/bot{TOKEN}"

DB_PATH = os.path.join(os.path.dirname(__file__), "joys.db")

POLL_TIMEOUT = 30
POLL_SLEEP = 1

# Тестовый режим с отчётом через 10 минут больше не используем
TEST_MODE = False

# Использовать ли LanguageTool для исправления орфографии/пунктуации.
USE_LANGTOOL = False
LANGTOOL_URL = "https://api.languagetool.org/v2/check"

# Небольшой список мата/нецензурной лексики (можно расширять)
BAD_WORDS = [
    "хуй", "хуи", "хер", "пизда", "ебать", "ебан", "сука", "бляд", "бля",
]

# Стоп-слова (не считаем их ключевыми) — простой набор, можно дополнять
STOPWORDS_RU = {
    "и", "в", "во", "на", "но", "а", "я", "ты", "он", "она", "оно", "мы", "вы", "они",
    "это", "как", "что", "чтобы", "когда", "там", "здесь", "тут", "про", "для", "из",
    "у", "с", "со", "от", "под", "над", "по", "за", "же", "ли", "не", "ни",
    "был", "была", "были", "есть", "буду", "будет", "будут",
    "мой", "моя", "моё", "мои", "твой", "твоя", "твоё", "твои",
    "его", "её", "их", "тут", "там", "тот", "та", "то", "те",
    "очень", "просто", "сегодня", "вчера", "завтра", "ещё", "уже",
}

# Фразы обычной грусти / упадка
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

# Фразы про сильную усталость / выгорание
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

# Фразы про тревогу / паники
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

# Более тяжёлые фразы, требующие особенной поддержки
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

# Приветствия
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

# Динамические эмодзи
JOY_EMOJIS = [
    "✨", "😊", "🌈", "💛", "🌟"
]

REMINDER_EMOJIS = [
    "✨", "📌", "😊"
]

STATS_EMOJIS = [
    "📊", "📈", "⭐"
]

ACHIEVEMENT_EMOJIS = [
    "🏅", "🎉", "🌟"
]

# Спокойные эмодзи для эмоциональных ответов
CALM_EMOJIS = ["🙂", "🌿", "✨", "☕", "🕊", "🍃"]

# Ответы на грусть — спокойные, поддерживающие
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

# Ответы на усталость — мягкие, спокойные
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

# Ответы на тревогу — менее эмоциональные, больше опоры
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

# Ответы на радости — спокойные, короткие
JOY_RESPONSES = [
    "Записала это как твою радость дня.",
    "Сохранила. Такой момент точно стоит помнить.",
    "Добавила в твой дневник хорошего.",
    "Отметила эту радость. Спасибо, что поделилась.",
    "Записала. Пусть это будет твоей маленькой опорой.",
]

# Пороги для ритуала «3 маленькие радости»
SAD_RITUAL_DAYS = 3        # за сколько дней смотрим
SAD_RITUAL_THRESHOLD = 3   # сколько тяжёлых событий за эти дни


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
    # тяжёлые/грустные/тревожные события (для ритуала)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sad_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    # эмоции сообщений (новая таблица)
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
    # ключевые слова радостей (новая таблица)
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
    """
    Сохраняем эмоцию сообщения (joy / sad / tired / anxiety / severe_sad / greeting / other).
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO message_emotions (chat_id, emotion, source_text, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (chat_id, emotion, source_text, created_at),
    )
    conn.commit()
    conn.close()


def add_joy_keyword(chat_id: int, keyword: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO joy_keywords (chat_id, keyword, created_at)
        VALUES (?, ?, ?)
        """,
        (chat_id, keyword, created_at),
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
    """
    Радости за конкретный день.
    """
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


def detect_emotion_label(text: str) -> str:
    """
    Возвращает грубую метку эмоции по тексту.
    Используем те же паттерны, что и для ответов.
    """
    cleaned = text.strip()
    if not cleaned:
        return "other"

    if is_severe_sad_message(cleaned):
        return "severe_sad"
    if is_anxiety_message(cleaned):
        return "anxiety"
    if is_tired_message(cleaned):
        return "tired"
    if is_sad_message(cleaned):
        return "sad"
    if is_greeting_message(cleaned):
        return "greeting"

    # Если дошли сюда — либо радость, либо нейтрально.
    return "other"


# --------------------------
# Выделение ключевых слов радости
# --------------------------

def extract_keywords(text: str, max_keywords: int = 5) -> List[str]:
    """
    Очень простой извлекатель ключевых слов:
    - приводит к нижнему регистру;
    - режет по не-буквенным символам;
    - выбрасывает слишком короткие слова и стоп-слова;
    - оставляет до max_keywords уникальных слов.
    """
    lower = text.lower()
    # разбиваем по всему, что не буква (рус/лат)
    raw_tokens = re.split(r"[^a-zA-Zа-яА-ЯёЁ]+", lower)
    keywords = []
    seen = set()

    for token in raw_tokens:
        token = token.strip()
        if len(token) < 4:
            continue
        if token in STOPWORDS_RU:
            continue
        if token in seen:
            continue
        seen.add(token)
        keywords.append(token)
        if len(keywords) >= max_keywords:
            break

    return keywords


def save_joy_keywords(chat_id: int, text: str):
    """
    Сохраняем ключевые слова радости в таблицу joy_keywords.
    """
    kws = extract_keywords(text)
    if not kws:
        return
    for kw in kws:
        add_joy_keyword(chat_id, kw)


# --------------------------
# Генерация текстов ответов
# --------------------------

def add_emoji_prefix(text: str) -> str:
    """Добавляет один спокойный эмодзи в начало ответа."""
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
                "Можно попробовать небольшой ритуал: сегодня перед сном отметь для себя три маленькие радости.\n"
                "Не обязательно что-то большое — еда, уют, спокойный момент. "
                "Если захочешь, можешь написать их мне."
            ),
        )


# --------------------------
# Еженедельный отчёт (пока не используем, но оставим)
# --------------------------

def send_weekly_report_for_user(chat_id: int):
    today_local = datetime.now().date()
    week_start = today_local - timedelta(days=6)
    joys = get_joys_for_week(chat_id, week_start)

    if not joys:
        send_message(
            chat_id,
            add_emoji_prefix(
                "Пока у меня нет сохранённых радостей за эту неделю.\n"
                "Если захочешь, сегодня можно начать с одной небольшой."
            )
        )
        return

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
    send_message(
        chat_id,
        f"{header}\n\n{body}"
    )


# --------------------------
# Ежедневный отчёт за день (в 22:00)
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
    send_message(
        chat_id,
        f"{header}\n\n{body}"
    )


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
        f"• Всего радостей: {total}\n"
        f"• За последние 7 дней: {last7}\n"
        f"• Текущий стрик по дням: {streak}\n"
        f"• Первая запись: {first_str}\n\n"
        "Ты уже проделала заметную работу для себя."
    )
    send_message(chat_id, msg)


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
            "В 19:00 я напомню, если ты ничего не написала, а в 22:00 пришлю небольшой отчёт за день."
        )
        # /start логически можно считать нейтральным
        add_message_emotion(chat_id, "start", stripped)
        return

    # /stats
    if stripped.startswith("/stats"):
        send_stats(chat_id)
        add_message_emotion(chat_id, "stats", stripped)
        return

    cleaned = clean_text_pipeline(text)
    if not cleaned:
        send_message(
            chat_id,
            "Мне не удалось ничего сохранить.\n"
            "Попробуй написать чуть конкретнее, что тебя сегодня порадовало."
        )
        add_message_emotion(chat_id, "other", text)
        return

    # Приветствие — отвечаем, но НЕ записываем как радость
    if is_greeting_message(cleaned):
        send_message(chat_id, get_greeting_response())
        add_message_emotion(chat_id, "greeting", cleaned)
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
        add_message_emotion(chat_id, "severe_sad", cleaned)
        maybe_offer_ritual(chat_id)
        return

    # тревога
    if is_anxiety_message(cleaned):
        send_message(chat_id, get_anxiety_response())
        add_sad_event(chat_id)
        add_message_emotion(chat_id, "anxiety", cleaned)
        maybe_offer_ritual(chat_id)
        return

    # усталость
    if is_tired_message(cleaned):
        send_message(chat_id, get_tired_response())
        add_sad_event(chat_id)
        add_message_emotion(chat_id, "tired", cleaned)
        maybe_offer_ritual(chat_id)
        return

    # грусть / «ничего хорошего»
    if is_sad_message(cleaned):
        send_message(chat_id, get_sad_response())
        add_sad_event(chat_id)
        add_message_emotion(chat_id, "sad", cleaned)
        maybe_offer_ritual(chat_id)
        return

    # Обычная радость (или нейтральное, но мы трактуем как радость для дневника)
    add_joy(chat_id, cleaned)
    save_joy_keywords(chat_id, cleaned)
    send_message(chat_id, get_joy_response())
    check_and_send_achievements(chat_id)
    add_message_emotion(chat_id, "joy", cleaned)


# --------------------------
# Еженедельный отчёт (боевой режим, пока не используем)
# --------------------------

def weekly_job_runner():
    print("Weekly job runner started (боевой режим).")
    already_sent_for_week = set()

    while True:
        now = datetime.now()
        if now.isoweekday() == 7 and now.hour == 19:
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
        time.sleep(60)


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

    # weekly_job_runner оставлен на будущее
    # t_weekly = threading.Thread(target=weekly_job_runner, daemon=True)
    # t_weekly.start()

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
