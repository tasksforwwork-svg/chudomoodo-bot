# chudomoodo_bot.py
"""
Telegram-бот "Дневник маленьких радостей".

Изменения и исправления:
- исправлена проблема с дублированием ответов (проверка processed_updates + in-memory дедупликация);
- приветствие/эмоции/радости обрабатываются только один раз (строго последовательный if/return);
- добавлена таблица future_letters и фоновый планировщик future_letters_runner,
  письма отправляются ровно через N дней в то же время, в которое были созданы;
- структурировано и объединено в один файл.
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
POLL_SLEEP = 0.5

# --------------------------
# EMOJI / RESPONSES (user-provided & curated)
# --------------------------

JOY_EMOJIS = ["✨", "😊", "🌈", "💛", "🌟"]
REMINDER_EMOJIS = ["✨", "📌", "😊"]
STATS_EMOJIS = ["📊", "📈", "⭐"]
CALM_EMOJIS = ["🙂", "🌿", "✨", "☕", "🕊", "🍃"]

GREETING_RESPONSES = [
    "Привет! Большое счастье состоит из маленьких мгновений. Какое из них запомнилось тебе сегодня?",
    "Салют! Я здесь. Пришли, пожалуйста, один хороший момент - даже если это просто смешной мем, который ты увидела.",
    "Ооооо))Рада тебя видеть здесь. Давай отметим что-нибудь приятное из этого дня?",
    "Привет! Предлагаю отправиться в самый обычный момент твоего дня и найти в нём что-то хорошее.",
    "Так, я тут. Загрузи сюда свою обязательную дневную радость - кофе, музыку или чью-то случайную адекватность.",
    "Привет. Начнём с простого: ты добралась до этого чата - уже успех. Что ещё сегодня было не провалом?)",
    "Хей! Первая радость - ты. Вторая - то, что ты сейчас мне расскажешь.",
    "Ооо, выглянула! Давай делиться чем-то хорошим — даже если оно размером с крошку от круассана.",
    "Привет! Давай честно: что сегодня было нормального и не бесило? Такие вещи надо уважать.",
    "Ооо, ты здесь! Подкинь событие, после которого ты не закатила глаза. Это редкость, коллекционный экземпляр!",
    "Ооо))) Самая простая радость случилась - ты появилась! Теперь давай вторую, пока победа не испарилась.",
    "Привет! Предлагаю стартануть с чего-то очевидного: что сегодня было твоим базовым минимумом? Еда, музыка или кофе?",
    "Я тут! Кидай свою победу дня. Даже если победила только собственную лень - мы такое уважаем!",
    "Рад, что ты заглянула! Давай, вспоминай: что в этот день было хорошего? Хоть что-то? Хоть кто-то?",
]

SAD_RESPONSES = [
    "Звучит как очень непростой день. Не обязательно прямо сейчас искать в нём плюсы.",
    "Если вдруг появится мысль вроде «кофе помог» — просто напиши. Я сохраню.",
    "Если позже вспомнится момент, когда на душе стало светлее — просто кинь его сюда. Я запомню.",
    "Понимаю, что сегодня могло быть тяжело. Ты всегда умница, даже если самой так не кажется.",
    "Понимаю, день мог быть тяжковатым — жизнь иногда любит драму.",
    "Но ты всё равно умница, даже когда ходишь в энергосберегающем режиме.",
    "Можешь даже одним словом описать момент, когда сегодня стало чуть спокойнее — даже если он длился секунду. Я запомню.",
    "Понимаю, что сегодня было тяжеловато. Не заставляй себя искать плюсы.",
    "Если вечером вспомнится что-то, что хоть на минуту отпустило — например «горячий душ» или «тишина» — пришли, я запишу.",
    "Вижу, что день был не сахар. И ничего придумывать не нужно.",
    "Если вдруг поймаешь себя на чём-то вроде «кофе помог» или «бестис прислала смешной мем» — просто напиши мне. Я запомню.",
    "Чувствую, что сегодня было нелегко. Не стоит форсировать хорошее.",
    "Если невзначай вспомнится момент, когда стало чуть легче — напиши в двух словах. Я сохраню как есть.",
]

TIRED_RESPONSES = [
    "Ловлю твоё настроение без слов. Если вдруг позже вспомнится что-то простое вроде «дождь закончился как по заказу» — я на подхвате!",
    "Всё нормально, я рядом. Не ты слабая — день был сильным. Если вдруг поймёшь, что ужин сегодня неожиданно был вкусным — это тоже радость. Пиши — я запомню!",
    "Ты не уставшая — ты герой без пафоса. Можно ничего не говорить.",
    "Если вдруг поймаешь себя на мысли «У меня же остались конфеты!» — это уже повод для нашего чата!",
    "Окей, вижу, что слов нет. Молчу как рыба.",
    "Если вдруг вспомнишь, как твой котик спал рядом — я на низком старте! Отправлю в нашу коллекцию радостей.",
    "Ты не сдаёшься — ты просто немного устала.",
    "Если вдруг вспомнится момент, когда стало хоть чуть-чуть светлее — это уже прорыв! Сообщи — запишем в наш архив побед.",
]

ANXIETY_RESPONSES = [
    "Похоже, твоя тревожность решила пройтись по всем сценариям сразу.",
    "Но это потому, что ты умеешь заранее видеть то, что другим приходит в голову через неделю.",
    "Так, слышу характерный звук: «загрузился новый уровень тревоги».",
    "Но если прислушаться — это всего лишь твоя внимательность, которая чуть перегнула палку.",
    "Так-так, тревога на горизонте! Но если присмотреться — это просто замаскированная забота о том, что тебе дорого.",
    "Слушай, а ведь твоя тревожка — это как суперспособность — гиперзабота о важном. Просто пока прокачана не до конца.",
    "Эх, смотрю, внутренний критик опять устроил драму, как в сериале. А ведь это просто твоя суперсила — замечать каждую мелочь!",
]

NO_JOY_RESPONSES = [
    "Ничего, что сегодня нечего написать. Бывает. Не переживай.",
    "Если вечером вспомнишь, что играла любимая песня или были классные скидки на WB — напиши мне. Я сохраню.",
    "Пустота в днях — это как пауза в музыке. Не обязательно её заполнять.",
    "Никаких обязательных радостей! Но если вдруг вспомнишь голубя со смешной походкой или неожиданный комплимент — это повод написать мне!",
    "Ничего, что сегодняшний день как чистый лист. Бывает и такое.",
    "Если вдруг вечером вспомнится что-то — я на низком старте.",
    "Разрешаю тебе сегодня просто побыть.",
    "Пустота — это не ошибка. Это пауза, которая тоже нужна.",
    "Бывает, когда «ничего» — это лучшее, что мир может предложить.",
    "Если после спокойствия появится что-то маленькое и приятное — я хочу об этом знать.",
]

JOY_RESPONSES = [
    "Зафиксировала и поставила печать: момент официально признан прекрасным.",
    "Твой момент отправлен в коллекцию «Такие штуки и спасают».",
    "Отправлено в наш фонд эмоциональной стабильности — теперь там на одну радость больше.",
    "Зафиксировала! Занесено в реестр улыбок!",
    "Отправлено в раздел внезапных радостей! Теперь этот момент застрахован от плохого настроения и будет доступен по первому требованию.",
    "Передано в отдел ценных воспоминаний!",
    "Сохранила в специальную папку «То, что греет душу».",
    "Заложила в фундамент нашего общего настроения!",
    "Отправлено в копилку! Пусть этот момент будет тем якорем, что держит на плаву в бурный день.",
    "Отправила в нашу папку счастливых мелочей! Теперь этот момент в безопасности — защищён от ежедневного хаоса и плохого настроения.",
    "Сохранила в разделе экстренной помощи настроению. Теперь это твой личный запас радости!",
    "Передала на хранение внутреннему ребёнку! Теперь это воспоминание будет периодически напоминать о себе в самые неожиданные моменты.",
    "Зафиксировала в журнале поводов для улыбки!",
    "Передано в отдел ценных мгновений! Этот момент теперь имеет статус неприкосновенного запаса хорошего настроения.",
]

# --------------------------
# DICTIONARIES (expanded but compact)
# --------------------------
# (оставлены компактные расширенные версии — можешь заменить на большие наборы)
BAD_WORDS = [
    # core russian obscene roots / variants (compact-expanded)
    "хуй", "хуё", "хует", "хуя", "хую", "хуёв", "хуета", "пизд", "пиздец", "пизда",
    "ебан", "ебать", "ёбан", "ёб", "ебу", "ебё", "ебло", "ебальн",
    "сука", "суки", "суч", "бляд", "блять", "бля", "блядина",
    "мраз", "твар", "гандон", "залуп", "хер", "херня", "говн", "говно",
    "долбоеб", "мудак", "мудила", "идиот", "урод", "пидор", "траха", "трахну",
    # some english swears
    "fuck", "fucking", "shit", "bitch", "asshole", "motherfucker",
    # mild obfuscations
    "х_й", "xuy", "pizd", "ebat", "ebat'", "eb*", "f**k", "s**t"
]

# regex to catch mangled obscene forms like ху-й, х*й, f u c k etc.
BAD_WORDS_REGEX = re.compile(
    r"(х[\W_]*у[\W_]*й|п[\W_]*и[\W_]*з[\W_]*д|е[\W_]*б[\W_]*а|ё[\W_]*б|бл[\W_]*я|f[\W_]*u[\W_]*c[\W_]*k|s[\W_]*h[\W_]*i[\W_]*t)",
    re.IGNORECASE
)

# For emotional pattern detection keep moderately wide lists
SAD_PATTERNS = [
    "ничего хорошего", "ничего не радует", "всё плохо", "все плохо", "ужасный день",
    "плохо", "очень плохо", "грустно", "мне грустно", "тоскливо", "одиночество",
    "нет надежды", "всё пропало", "жизнь бессмысленна", "безысходность", "опустил руки",
    "опустила руки", "сердце болит", "на душе пусто", "не вижу радости", "не хочу ничего"
]

TIRED_PATTERNS = [
    "устала", "устал", "нет сил", "совсем нет сил", "вымоталась", "вымотался",
    "выгорела", "вымотана", "я не могу", "не тяну", "батарейка села", "энергия на нуле",
    "не выспалась", "не выспался", "недосып", "хочется спать", "усталость", "истощена"
]

ANXIETY_PATTERNS = [
    "боюсь", "мне страшно", "тревожно", "паника", "панические атаки", "паникую",
    "переживаю", "очень переживаю", "волнует", "не могу перестать думать", "боюсь ошибиться",
    "сердце колотится", "не хватает воздуха", "задыхаюсь", "тревога"
]

SEVERE_SAD_PATTERNS = [
    "не хочу жить", "хочу умереть", "думаю о самоубийстве", "суицидальные мысли", "лучше бы меня не было",
    "готова покончить", "готов покончить", "прощаюсь", "планирую суицид"
]

NO_JOY_PATTERNS = [
    "не знаю что написать", "ничего не было", "пусто", "ничего хорошего не было", "не знаю", "ничего"
]

# Greeting variants (compact but broad)
GREETINGS = [
    "привет", "привет!", "приветик", "прив", "здравствуй", "здравствуйте",
    "добрый день", "доброе утро", "добрый вечер", "хай", "хелло", "hello", "hi", "hey",
    "ку", "йоу", "ghbdtn", "privet"
]

CANCEL_PATTERNS = ["отмена", "отменить", "/cancel", "стоп", "не хочу", "я передумал", "я передумала"]

# --------------------------
# TELEGRAM API helpers
# --------------------------

def tg_post(method: str, payload: dict):
    """Simple wrapper for Telegram POST requests."""
    url = f"{API_URL}/{method}"
    try:
        r = requests.post(url, json=payload, timeout=15)
        return r.json()
    except Exception as e:
        print("tg_post error:", e)
        return None

def send_message(chat_id: int, text: str):
    tg_post("sendMessage", {"chat_id": chat_id, "text": text})

def get_updates(offset: Optional[int] = None, timeout: int = POLL_TIMEOUT) -> List[dict]:
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    try:
        r = requests.get(f"{API_URL}/getUpdates", params=params, timeout=timeout + 5)
        js = r.json()
        if not js.get("ok"):
            return []
        return js.get("result", [])
    except Exception as e:
        # network or parsing error -> return empty
        # print("get_updates error:", e)
        return []

# --------------------------
# DATABASE
# --------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS joys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sad_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS future_letters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            send_at TEXT NOT NULL,
            sent INTEGER DEFAULT 0,
            sent_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sent_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            reminder_date TEXT NOT NULL,
            reminder_type TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE(chat_id, reminder_date, reminder_type)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS processed_updates (
            update_id INTEGER PRIMARY KEY,
            processed_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

# Joys / sad events / future letters helpers

def add_joy(chat_id: int, text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute("INSERT INTO joys (chat_id, text, created_at) VALUES (?, ?, ?)", (chat_id, text, now))
    conn.commit()
    conn.close()

def add_sad_event(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute("INSERT INTO sad_events (chat_id, created_at) VALUES (?, ?)", (chat_id, now))
    conn.commit()
    conn.close()

def add_future_letter(chat_id: int, text: str, days: int, created_at: Optional[datetime] = None):
    """
    Сохраняет письмо в future_letters. send_at = created_at + days.
    Если created_at не указан — берём сейчас.
    """
    created = created_at or datetime.now()
    send_at = created + timedelta(days=days)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO future_letters (chat_id, text, created_at, send_at, sent) VALUES (?, ?, ?, ?, 0)",
        (chat_id, text, created.isoformat(timespec="seconds"), send_at.isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()

def get_due_future_letters(now_dt: datetime) -> List[dict]:
    """
    Возвращает письма, срок отправки которых <= now_dt и которые ещё не отправлены.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, chat_id, text, created_at, send_at FROM future_letters WHERE sent = 0 AND send_at <= ?", (now_dt.isoformat(timespec="seconds"),))
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "chat_id": r[1],
            "text": r[2],
            "created_at": r[3],
            "send_at": r[4]
        })
    return result

def mark_future_letter_sent(letter_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute("UPDATE future_letters SET sent = 1, sent_at = ? WHERE id = ?", (now, letter_id))
    conn.commit()
    conn.close()

def get_joy_count(chat_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM joys WHERE chat_id = ?", (chat_id,))
    cnt = cur.fetchone()[0]
    conn.close()
    return cnt

def get_todays_joys(chat_id: int) -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    today = date.today().isoformat()
    cur.execute("SELECT text, created_at FROM joys WHERE chat_id = ? AND substr(created_at,1,10) = ? ORDER BY created_at ASC", (chat_id, today))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def has_joy_for_date(chat_id: int, date_obj: date) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM joys WHERE chat_id = ? AND substr(created_at,1,10) = ?", (chat_id, date_obj.isoformat()))
    cnt = cur.fetchone()[0]
    conn.close()
    return cnt > 0

def get_all_user_ids() -> List[int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT chat_id FROM joys")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def has_sent_reminder_today(chat_id: int, reminder_type: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    today = date.today().isoformat()
    cur.execute("SELECT COUNT(*) FROM sent_reminders WHERE chat_id = ? AND reminder_date = ? AND reminder_type = ?", (chat_id, today, reminder_type))
    cnt = cur.fetchone()[0]
    conn.close()
    return cnt > 0

def mark_reminder_sent(chat_id: int, reminder_type: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    try:
        cur.execute("INSERT INTO sent_reminders (chat_id, reminder_date, reminder_type, sent_at) VALUES (?, ?, ?, ?)", (chat_id, today, reminder_type, now))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

# processed_updates helpers to avoid double-processing of the same update_id
def mark_update_processed(update_id: int) -> bool:
    """
    Возвращает True, если мы пометили update как обработанный впервые.
    Возвращает False, если уже был такой update_id.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    try:
        cur.execute("INSERT INTO processed_updates (update_id, processed_at) VALUES (?, ?)", (update_id, now))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# --------------------------
# TEXT CLEANING & PROFANITY
# --------------------------

def normalize_text_for_match(t: str) -> str:
    if t is None:
        return ""
    return " ".join(t.lower().replace("ё", "е").split())

def contains_profanity(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    for w in BAD_WORDS:
        if w in t:
            return True
    if BAD_WORDS_REGEX.search(t):
        return True
    return False

def clean_profanity(text: str) -> str:
    if not text:
        return ""
    s = text
    for bad in BAD_WORDS:
        # replace occurrences with asterisks of same length (case-insensitive)
        s = re.sub(re.escape(bad), lambda m: "*" * len(m.group(0)), s, flags=re.IGNORECASE)
    # also apply regex-based masking
    s = BAD_WORDS_REGEX.sub(lambda m: "*" * len(m.group(0)), s)
    return s

def clean_text_pipeline(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    if not t:
        return ""
    t = clean_profanity(t)
    return t

# --------------------------
# MOOD RECOGNITION
# --------------------------

def is_greeting_message(text: str) -> bool:
    t = normalize_text_for_match(text)
    # limit length to avoid long texts being mistaken for greeting
    if len(t) > 40:
        return False
    return any(t == g or t.startswith(g + " ") or t.startswith(g + "!") or t.startswith(g + ")") for g in GREETINGS)

def is_severe_sad_message(text: str) -> bool:
    t = normalize_text_for_match(text)
    return any(p in t for p in SEVERE_SAD_PATTERNS)

def is_sad_message(text: str) -> bool:
    t = normalize_text_for_match(text)
    return any(p in t for p in SAD_PATTERNS)

def is_tired_message(text: str) -> bool:
    t = normalize_text_for_match(text)
    return any(p in t for p in TIRED_PATTERNS)

def is_anxiety_message(text: str) -> bool:
    t = normalize_text_for_match(text)
    return any(p in t for p in ANXIETY_PATTERNS)

def is_no_joy_message(text: str) -> bool:
    t = normalize_text_for_match(text)
    return any(p in t for p in NO_JOY_PATTERNS)

def is_cancel_message(text: str) -> bool:
    t = normalize_text_for_match(text)
    return any(t == c or t.startswith(c + " ") for c in CANCEL_PATTERNS)

def is_wantnow_message(text: str) -> bool:
    t = normalize_text_for_match(text)
    # accept different variants
    return t in {"wantnow", "хочу отчет", "дай отчёт", "отчёт за сегодня", "отчет за сегодня", "report", "today report"}

# --------------------------
# RESPONSE GENERATORS
# --------------------------

def add_emoji_prefix(text: str) -> str:
    return f"{random.choice(CALM_EMOJIS)} {text}"

def get_greeting_response() -> str:
    return add_emoji_prefix(random.choice(GREETING_RESPONSES))

def get_sad_response() -> str:
    return add_emoji_prefix(random.choice(SAD_RESPONSES))

def get_tired_response() -> str:
    return add_emoji_prefix(random.choice(TIRED_RESPONSES))

def get_anxiety_response() -> str:
    return add_emoji_prefix(random.choice(ANXIETY_RESPONSES))

def get_no_joy_response() -> str:
    return add_emoji_prefix(random.choice(NO_JOY_RESPONSES))

LAST_JOY_INDEX: Dict[int, int] = {}

def get_joy_response(chat_id: int) -> str:
    if not JOY_RESPONSES:
        return add_emoji_prefix("Записала это как твою радость.")
    last_idx = LAST_JOY_INDEX.get(chat_id)
    idx = random.randrange(len(JOY_RESPONSES))
    if last_idx is not None and len(JOY_RESPONSES) > 1:
        tries = 0
        while idx == last_idx and tries < 5:
            idx = random.randrange(len(JOY_RESPONSES))
            tries += 1
    LAST_JOY_INDEX[chat_id] = idx
    return add_emoji_prefix(JOY_RESPONSES[idx])

def get_wantnow_report(chat_id: int) -> str:
    today = date.today()
    rows = get_todays_joys(chat_id)
    if not rows:
        return add_emoji_prefix("Сегодня пока нет записанных радостей.")
    report = f"{random.choice(JOY_EMOJIS)} Вот что хорошего было сегодня:\n\n"
    for i, r in enumerate(rows, 1):
        report += f"{i}. {r}\n"
    return report

# --------------------------
# DEDUP: in-memory short window to mitigate duplicates from Telegram
# --------------------------

_last_messages: Dict[int, Tuple[str, float]] = {}
# short window seconds - prevents duplicate reaction to same incoming text within that window
DUPLICATE_WINDOW = 3.0

def is_recent_duplicate(chat_id: int, text: str) -> bool:
    now_ts = time.time()
    key = chat_id
    last = _last_messages.get(key)
    norm = text.strip()
    if last:
        last_text, last_ts = last
        if last_text == norm and (now_ts - last_ts) <= DUPLICATE_WINDOW:
            return True
    _last_messages[key] = (norm, now_ts)
    return False

# --------------------------
# HANDLING INCOMING MESSAGES
# --------------------------

def handle_message_once(chat_id: int, text: str):
    """
    Главная логика обработки одного сообщения. Гарантирует только ОДИН ответ.
    """
    if not text or not text.strip():
        return

    if is_recent_duplicate(chat_id, text):
        # молча игнорируем быстрые дубли
        return

    stripped = text.strip()

    # COMMANDS - highest priority
    if stripped.startswith("/start"):
        # clear nothing persistent - just greet
        send_message(chat_id,
            "Привет. Я помогу тебе замечать и сохранять маленькие радости.\n\n"
            "Каждый день можно писать сюда что-то приятное из дня.\n"
            "В 19:00 я напомню, если ты ничего не написала, а в 21:00 пришлю отчёт за день.\n\n"
            "Можешь начать уже сейчас!"
        )
        return

    if stripped.startswith("/stats"):
        total = get_joy_count(chat_id)
        if total == 0:
            send_message(chat_id, f"{random.choice(STATS_EMOJIS)} Пока у тебя нет записанных радостей.")
        else:
            send_message(chat_id, f"{random.choice(STATS_EMOJIS)} У тебя уже {total} записанных радостей!")
        return

    if stripped.startswith("/letter"):
        # start letter dialog - ask period
        set_dialog_state(chat_id, "await_letter_period", None)
        send_message(chat_id, add_emoji_prefix(
            "Давай устроим маленькое письмо в будущее.\n\n"
            "Выбери, когда хочешь его получить:\n• 7 — через неделю\n• 14 — через две недели\n• 30 — через месяц\n\n"
            "Просто напиши цифру: 7, 14 или 30. Если передумаешь — напиши /cancel."
        ))
        return

    if stripped.startswith("/cancel"):
        state, meta = get_dialog_state(chat_id)
        clear_dialog_state(chat_id)
        if state:
            send_message(chat_id, add_emoji_prefix("Окей, отменила текущий диалог."))
        else:
            send_message(chat_id, add_emoji_prefix("Нечего отменять."))
        return

    # If user in letter dialog
    state, meta = get_dialog_state(chat_id)
    if state == "await_letter_period":
        # expect "7", "14", "30"
        norm = normalize_text_for_match(stripped)
        if is_cancel_message(stripped):
            clear_dialog_state(chat_id)
            send_message(chat_id, add_emoji_prefix("Окей, письмо не будет сохранено."))
            return
        if norm not in {"7", "14", "30"}:
            send_message(chat_id, add_emoji_prefix("Не поняла срок. Напиши только 7, 14 или 30 (число дней)."))
            return
        days = int(norm)
        set_dialog_state(chat_id, "await_letter_text", {"days": days})
        send_message(chat_id, add_emoji_prefix("Отлично. Напиши сейчас письмо себе — пару строк."))
        return

    if state == "await_letter_text":
        if is_cancel_message(stripped):
            clear_dialog_state(chat_id)
            send_message(chat_id, add_emoji_prefix("Окей, письмо отменено."))
            return
        days = (meta or {}).get("days", 7)
        cleaned = stripped
        if not cleaned:
            send_message(chat_id, add_emoji_prefix("Письмо пустое — напиши пару строк или /cancel."))
            return
        # Save future letter: created at now, send_at = now + days
        created_at = datetime.now()
        add_future_letter(chat_id, cleaned, days, created_at=created_at)
        # Also save as joy marker (optional) — but per request we will NOT save as joy; only future_letters
        clear_dialog_state(chat_id)
        send_message(chat_id, add_emoji_prefix(f"Отлично! Сохранила твоё письмо. Напомню о нём через {days} дней."))
        return

    # profanity check
    if contains_profanity(stripped):
        send_message(chat_id, add_emoji_prefix("Похоже, сегодня был трудный день. Понимаю, но давай попробуем обойтись без резких слов."))
        return

    # wantnow report
    if is_wantnow_message(stripped):
        send_message(chat_id, get_wantnow_report(chat_id))
        return

    # greeting
    if is_greeting_message(stripped):
        send_message(chat_id, get_greeting_response())
        return

    # severe sad -> special handling
    if is_severe_sad_message(stripped):
        send_message(chat_id, add_emoji_prefix(
            "Слышу, что тебе сейчас очень тяжело.\n\n"
            "Постарайся поговорить с тем, кому доверяешь: близкий человек или специалист. Если есть опасность для жизни — обратись в службы помощи."
        ))
        add_sad_event(chat_id)
        return

    # anxiety / tired / sad (one response only)
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

    # standard joy: clean text and save
    cleaned = clean_text_pipeline(stripped)
    if cleaned:
        add_joy(chat_id, cleaned)
        send_message(chat_id, get_joy_response(chat_id))
        return

    # fallback
    send_message(chat_id, add_emoji_prefix("Не совсем поняла — напиши чуть по-другому, пожалуйста."))

# --------------------------
# DIALOG STATE (in-memory simple store)
# --------------------------
# note: kept in-memory; can be extended to DB if persistence over restarts needed

_dialog_states: Dict[int, Dict] = {}

def set_dialog_state(chat_id: int, state: str, meta: Optional[dict]):
    _dialog_states[chat_id] = {"state": state, "meta": meta, "updated_at": datetime.now().isoformat()}

def get_dialog_state(chat_id: int) -> Tuple[Optional[str], Optional[dict]]:
    rec = _dialog_states.get(chat_id)
    if not rec:
        return None, None
    return rec.get("state"), rec.get("meta")

def clear_dialog_state(chat_id: int):
    if chat_id in _dialog_states:
        del _dialog_states[chat_id]

# --------------------------
# DAILY REMINDERS & REPORTS (background threads)
# --------------------------

def daily_reminder_runner():
    """
    Напоминание в 19:00 — если за день нет радости.
    Отправляется однократно в день, через таблицу sent_reminders.
    """
    print("[scheduler] reminder thread started.")
    while True:
        now = datetime.now()
        # check at minute 00 (give 60s window)
        if now.hour == 19 and 0 <= now.minute < 2:
            today = now.date()
            for uid in get_all_user_ids():
                try:
                    if not has_joy_for_date(uid, today):
                        if not has_sent_reminder_today(uid, "reminder"):
                            send_message(uid, f"{random.choice(REMINDER_EMOJIS)} Привет! Напоминаю, что сегодня ты ещё не записала ни одной радости.\nМожет, что-то всё же было приятным?")
                            mark_reminder_sent(uid, "reminder")
                except Exception as e:
                    print("reminder error for", uid, e)
            # sleep to avoid double-sending within the same minute
            time.sleep(61)
        time.sleep(10)

def send_daily_report_for_user(uid: int):
    """Сформировать и отправить отчёт за текущий день"""
    today = date.today()
    if has_sent_reminder_today(uid, "report"):
        return
    joys = get_todays_joys(uid)
    if joys:
        report = f"{random.choice(JOY_EMOJIS)} Вот и подходит к концу этот день.\n\nВот твои радости за сегодня:\n\n"
        for i, j in enumerate(joys, 1):
            report += f"{i}. {j}\n"
        report += "\nСпокойной ночи!"
    else:
        report = f"{random.choice(CALM_EMOJIS)} День подошёл к концу. Завтра будет новый шанс заметить что-то хорошее.\nОтдыхай и набирайся сил."
    send_message(uid, report)
    mark_reminder_sent(uid, "report")

def daily_report_runner():
    """
    Отчёт в 21:00 — отправляется однократно в день.
    """
    print("[scheduler] daily report thread started.")
    while True:
        now = datetime.now()
        if now.hour == 21 and 0 <= now.minute < 2:
            for uid in get_all_user_ids():
                try:
                    send_daily_report_for_user(uid)
                except Exception as e:
                    print("daily_report error for", uid, e)
            time.sleep(61)
        time.sleep(10)

# --------------------------
# FUTURE LETTERS RUNNER
# --------------------------

def future_letters_runner():
    """
    Периодически (каждую минуту) проверяем таблицу future_letters
    и отправляем письма, сроки которых наступили (send_at <= now),
    а затем помечаем их sent = 1.
    Письмо отправляется в то же время, что задано в send_at (send_at хранит точное время).
    """
    print("[scheduler] future letters thread started.")
    while True:
        now = datetime.now()
        due = get_due_future_letters(now)
        for letter in due:
            try:
                cid = letter["chat_id"]
                text = letter["text"]
                send_at = letter["send_at"]
                # send message — prefaced
                send_message(cid, add_emoji_prefix("Письмо себе из прошлого:"))
                send_message(cid, text)
                # mark sent
                mark_future_letter_sent(letter["id"])
            except Exception as e:
                print("future letter send error:", e)
        # check every 30 seconds
        time.sleep(30)

# --------------------------
# POLLING LOOP
# --------------------------

def polling_loop():
    print("Polling loop started.")
    offset = None
    while True:
        try:
            updates = get_updates(offset, timeout=POLL_TIMEOUT)
            if not updates:
                time.sleep(POLL_SLEEP)
                continue
            for upd in updates:
                update_id = upd.get("update_id")
                if update_id is None:
                    continue
                # If we cannot insert processed_updates -> already processed: skip
                if not mark_update_processed(update_id):
                    # already processed
                    offset = update_id + 1
                    continue
                offset = update_id + 1
                # extract message
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = msg.get("text", "") or msg.get("caption", "") or ""
                if chat_id and text is not None:
                    try:
                        handle_message_once(chat_id, text)
                    except Exception as e:
                        print("handle_message_once error:", e)
            time.sleep(POLL_SLEEP)
        except Exception as e:
            print("polling error:", e)
            time.sleep(1)

# --------------------------
# START / THREADS
# --------------------------

def start_bot():
    print("Starting bot...")
    init_db()

    # scheduler threads
    t1 = threading.Thread(target=daily_reminder_runner, daemon=True)
    t1.start()

    t2 = threading.Thread(target=daily_report_runner, daemon=True)
    t2.start()

    t3 = threading.Thread(target=future_letters_runner, daemon=True)
    t3.start()

    # main poll loop (blocking)
    polling_loop()

if __name__ == "__main__":
    start_bot()
