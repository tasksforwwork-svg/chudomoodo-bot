"""
chudomoodo_bot.py

Telegram-бот "Дневник маленьких радостей".

Обновления:
- реагирует на приветствия + сам первым приветствует после /start;
- одна реакция на грусть / тревогу / усталость (без второго сообщения-диалога);
- напоминание в 18:00, отчёт за день в 21:00;
- более чувствительная реакция на «не знаю, что написать» и похожие фразы;
- мат не записывается как радость и не попадает в отчёты;
- отчёты фильтруют пустые / нейтральные фразы типа «не знаю, что написать»;
- расширены словари приветствий, грусти, тревоги, усталости, "не знаю";
- стиль ответов стал мягче и более «человеческим».
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

# Расширенный список мата / оскорблений (можно дополнять)
BAD_WORDS = [
    # базовые
    "хуй", "хуи", "хер", "пизда", "ебать", "ебан", "сука", "бляд", "бля",
    "ебло", "ебальник", "ебанут", "уебок", "уёбок", "уебан", "пидор",
    "пидар", "пидорас", "мразь", "тварь", "гандон", "гондон", "мудак",
    "долбоеб", "долбоёб", "идиот", "ебаный", "ебаная", "ебаное",
    "охуел", "охуела", "охуенно", "охуительный", "пошел на хуй",
    "пошёл на хуй", "пошла на хуй",
    # мягче, но всё равно нежелательно
    "офигеть", "офигенно", "обосрался", "обосралась", "сраный", "срань",
    "дерьмо", "говно", "задница", "жопа", "задница", "придурок", "придурочная",
    # вариации и сленг (можно дополнять)
    "сука блять", "сука бл", "хренотень", "хренота", "хреновый",
    "козлина", "козел", "козёл", "скотина",
]

# Грусть, опустошение, тоска
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
    "очень плохо",
    "тяжело",
    "грустно",
    "очень грустно",
    "хреново",
    "депрессивно",
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
    "я плачу",
    "хочу плакать",
    "плакать хочется",
    "душно на душе",
    "на душе тяжело",
    "на душе пусто",
    "пусто внутри",
    "внутри пустота",
    "нет сил радоваться",
    "ничего не хочется",
    "не хочу ничего",
    "опять всё не так",
    "снова всё плохо",
    "снова плохо",
]

# Усталость, выгорание
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
    "нет энергии",
    "совсем нет энергии",
    "я без сил",
    "я как выжатый лимон",
    "как выжатый лимон",
    "просто хочу лечь",
    "хочу спать и ничего не делать",
    "ужасно устала",
    "ужасно устал",
    "морально устала",
    "морально устал",
    "эмоционально устала",
    "эмоционально устал",
]

# Тревога, сомнения, страх
ANXIETY_PATTERNS = [
    "боюсь",
    "мне страшно",
    "страшно",
    "переживаю",
    "я переживаю",
    "тревожно",
    "меня трясет",
    "меня трясёт",
    "паника",
    "паникую",
    "вдруг не получится",
    "вдруг не выйдет",
    "я не уверена",
    "я неуверенна",
    "я не уверен",
    "волнуюсь",
    "я волнуюсь",
    "я все испортила",
    "я все испортил",
    "боюсь ошибиться",
    "очень переживаю",
    "мне неспокойно",
    "внутри тревога",
    "внутри паника",
    "сердце колотится",
    "накручиваю себя",
    "накручиваю",
]

# Сильные тяжёлые фразы
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

# «Не знаю, что написать» / пустота / ступор
NO_JOY_PATTERNS = [
    "не знаю что написать",
    "не знаю, что написать",
    "не знаю что добавить",
    "не знаю, что добавить",
    "не знаю что сказать",
    "не знаю, что сказать",
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
    "не знаю о чём написать",
    "не знаю о чем написать",
    "голова пустая",
    "в голове пусто",
    "ничего особенного",
    "не произошло ничего особенного",
    "не было ничего особенного",
]

# Отмена диалогов / писем
CANCEL_PATTERNS = [
    "отмена",
    "отменить",
    "я передумала",
    "я передумал",
    "не хочу писать",
    "не хочу письмо",
    "не хочу продолжать",
    "не хочу этого",
]

# Приветствия (сильно расширены; можно дополнять)
GREETING_PATTERNS = [
    "привет", "приветик", "приветики", "приветики)", "привет)", "привет!", "приветик!",
    "прив", "прив)", "прив!", "хай", "хай!", "ку", "ку!", "здравствуйте", "здраствуйте",
    "здравствуй", "доброго дня", "доброго времени суток", "добрый день", "добрый вечер",
    "доброе утро", "йоу", "йо", "йоу!", "йо!", "хеллоу", "хэллоу", "хелло", "хелло!",
    "hello", "hi", "hi!", "hey", "hey!", "здорово", "здарова", "здарова!", "здаров",
    "салют", "салют!", "бонжур", "бонжур!", "hola", "hola!",
]

GREETING_RESPONSES = [
    "Привет. Как твой день? Расскажешь что-нибудь маленькое, но приятное?",
    "Привет, я тут. Можешь скинуть одну радость за сегодня — даже если это просто вкусный чай.",
    "Рада видеть тебя здесь. Давай отметим что-нибудь тёплое из этого дня?",
    "Привет. Если хочешь, можем вместе поискать маленький светлый момент в твоём дне.",
    "Хей. Здесь можно выдохнуть и вспомнить хотя бы одну вещь, за которую сегодня можно тихо сказать себе «спасибо».",
]

JOY_EMOJIS = ["✨", "😊", "🌈", "💛", "🌟"]
REMINDER_EMOJIS = ["✨", "📌", "😊"]
STATS_EMOJIS = ["📊", "📈", "⭐"]
CALM_EMOJIS = ["🙂", "🌿", "✨", "☕", "🕊", "🍃"]

# Ответы на грусть
SAD_RESPONSES = [
    "Кажется, день выдался тяжёлым. Не обязательно прямо сейчас искать в нём плюсы. "
    "Если позже всплывёт момент, где стало хоть чуть спокойнее — напиши, я его бережно сохраню.",
    "Слышу, что сегодня было много тяжести. Иногда единственное хорошее — то, что день закончился. "
    "Если когда-нибудь вспомнишь что-то тёплое про этот день, я буду рядом.",
    "Бывает, что кажется: «ничего хорошего». Это ощущение тоже имеет право быть. "
    "Если позже заметишь хотя бы маленький мягкий момент — я аккуратно добавлю его в твою копилку.",
    "Похоже, внутри сейчас больше темных оттенков, чем светлых. "
    "Не надо себя за это ругать. Просто знай: когда появится хотя бы малая опора, ты сможешь поделиться ей здесь.",
    "То, что ты вообще смогла написать про своё состояние — это уже шаг. "
    "Иногда радость — это не про улыбку, а просто про то, что ты не отпускаешь себя из виду.",
]

# Ответы на усталость
TIRED_RESPONSES = [
    "Слышу сильную усталость. Похоже, ты очень много на себе несёшь. "
    "Иногда лучшая радость дня — это момент, когда можно просто выдохнуть и ничего не делать.",
    "Похоже, батарейка сегодня почти на нуле. Это не делает тебя слабой, это значит, что тебе много пришлось выдержать. "
    "Если вспомнишь маленький эпизод отдыха — чай, душ, паузу — можем его сохранить.",
    "Очень знакомое ощущение: «нет сил ни на что». "
    "Пусть этот день пока просто будет. А когда появится хотя бы крошечный момент отдыха — напиши мне о нём.",
    "День явно забрал много энергии. Ты всё равно дошла до этого момента — уже немало. "
    "Если захочешь, можешь отметить что-то, что помогло выдержать всё это.",
    "Иногда один из самых ценных моментов дня — это тот, где ты позволила себе остановиться. "
    "Если у тебя был такой кусочек времени, можешь рассказать о нём.",
]

# Ответы на тревогу
ANXIETY_RESPONSES = [
    "Чувствуется тревога. Обычно она приходит не просто так — значит, для тебя действительно что-то важно. "
    "Если получится, попробуй вспомнить момент, когда стало хоть немного спокойнее, и напиши мне о нём.",
    "Слышу, что внутри много волнения. Это нормальная реакция, когда вокруг много неопределённости. "
    "Ты можешь опереться хотя бы на один момент сегодняшнего дня, где всё не рушилось.",
    "Тревога умеет накручивать любые мысли до предела. "
    "Давай не будем требовать от себя идеального спокойствия. Если вспомнится маленький эпизод поддержки — я его сохраню.",
    "Сейчас может казаться, что всё хрупко. "
    "Но всё-таки ты уже справлялась с многими ситуациями раньше. Если захочешь, можешь отметить один момент, где ты выдержала сегодняшний день.",
    "Мысли могут бегать по кругу, и это выматывает. "
    "Иногда помогает вернуться к чему-то очень простому — еде, тёплому чаю, человеку рядом. "
    "Если такой момент был, можно его здесь оставить.",
]

# Нейтральные ответы на «не знаю, что написать»
NO_JOY_RESPONSES = [
    "Нормально не знать, что сказать. Мозг тоже иногда устает. "
    "Если позже всплывёт хоть маленький приятный момент — просто напиши.",
    "Окей, оставим этот день без формальных радостей. "
    "Если что-то тёплое случится чуть позже — здесь всегда есть место, чтобы это сохранить.",
    "Иногда кажется, что в дне не за что зацепиться. "
    "Можно ничего из себя не вытаскивать. Если что-то всё-таки всплывёт — я рядом.",
    "Пусть сегодня будет пауза. "
    "Иногда даже она — уже забота о себе. Если захочешь, ты сможешь вернуться в любой момент.",
]

# Ответы на сохранённые радости
JOY_RESPONSES = [
    "Сохранила это в копилку хороших моментов.",
    "Записала. Пусть это будет маленькой опорой на твой день.",
    "Оставила этот момент здесь, чтобы он не потерялся в суете.",
    "Добавила к твоим радостям. К ним всегда можно будет вернуться.",
    "Сложила это в твой личный запас тёплых воспоминаний.",
    "Записала. Когда-нибудь ты перечитаешь и улыбнёшься этому дню.",
    "Бережно сохранила. Ты правда умеешь замечать хорошее.",
    "Этот момент уже в твоём дневнике радостей.",
    "Положила эту радость в твой внутренний «альбом хорошего».",
    "Записала как напоминание: даже в сложные дни у тебя есть живые тёплые моменты.",
    "Сохранила это как маленькую заметку о том, что жизнь — не только про тяжесть.",
]

# Параметры для ритуала грусти (пока оставляем, но без доп. сообщений)
SAD_RITUAL_DAYS = 3
SAD_RITUAL_THRESHOLD = 3

# Темы радостей (для персонализации в статистике и обзорах)
THEME_KEYWORDS: Dict[str, List[str]] = {
    "еда": [
        "кофе", "чай", "какао", "печень", "печенье", "пицца", "торт", "тортик",
        "десерт", "шоколад", "конфет", "конфета", "шоколадка", "обед", "ужин",
        "завтрак", "кафе", "рестора", "булоч", "круассан", "вкусно", "фрукты",
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
        "отдых", "отдохнула", "отдохнул", "полежала", "полежал",
        "ничего не делала", "ничего не делал", "выспалась", "выспался", "сон",
        "спала", "спал", "релакс", "расслабилась", "расслабился", "ванна",
        "маска для лица", "спа", "тишина", "покой", "паузу", "передышка",
    ],
    "успехи": [
        "сделала", "сделал", "успела", "успел", "закончила", "закончил",
        "сдала", "сдал", "получилось", "справилась", "справился", "доделала",
        "доделал", "выполнила", "выполнил", "отчиталась", "отчитался",
        "похвалили", "похвала", "результат", "достигла", "достиг", "прогресс",
        "шаг вперёд", "шаг вперед",
    ],
}

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


def get_joys_between(chat_id: int, start_date: date, end_date: date) -> List[Tuple[str, str]]:
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
    cur.execute("SELECT COUNT(*) FROM joys WHERE chat_id = ?", (chat_id,))
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


# dialog_state helpers

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
    cur.execute("SELECT state, meta FROM dialog_state WHERE chat_id = ?", (chat_id,))
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


# future_letters helpers

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
    cur.execute("UPDATE future_letters SET sent = 1 WHERE id = ?", (letter_id,))
    conn.commit()
    conn.close()


# --------------------------
# Текстовая обработка
# --------------------------

def normalize_text_for_match(text: str) -> str:
    lower = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^\w\s]+", " ", lower)
    normalized = " ".join(normalized.split())
    return normalized


def contains_profanity(text: str) -> bool:
    norm = normalize_text_for_match(text)
    return any(bad in norm for bad in BAD_WORDS)


def clean_profanity(text: str) -> str:
    # заменяем мат на ***
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
    return any(
        lower == p or lower.startswith(p + " ")
        for p in GREETING_PATTERNS
    )


def is_no_joy_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    return any(p in lower for p in NO_JOY_PATTERNS)


def is_cancel_message(text: str) -> bool:
    lower = normalize_text_for_match(text)
    return any(p in lower for p in CANCEL_PATTERNS)


# --------------------------
# Темы радостей
# --------------------------

def classify_joy_themes(text: str) -> List[str]:
    result = []
    norm = normalize_text_for_match(text)
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in norm:
                result.append(theme)
                break
    return result


def summarize_themes(theme_counts: Dict[str, int]) -> Optional[str]:
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


def get_joy_response(chat_id: int) -> str:
    if not JOY_RESPONSES:
        return add_emoji_prefix("Сохранила это как твою радость.")
    last_idx = LAST_JOY_INDEX.get(chat_id)
    idx = random.randrange(len(JOY_RESPONSES))
    if last_idx is not None and len(JOY_RESPONSES) > 1:
        for _ in range(3):
            if idx != last_idx:
                break
            idx = random.randrange(len(JOY_RESPONSES))
    LAST_JOY_INDEX[chat_id] = idx
    return add_emoji_prefix(JOY_RESPONSES[idx])


def get_no_joy_response() -> str:
    return add_emoji_prefix(random.choice(NO_JOY_RESPONSES))


# --------------------------
# Ачивки (аккуратные)
# --------------------------

def check_and_send_achievements(chat_id: int):
    total = get_joy_count(chat_id)
    streak = get_current_streak(chat_id)

    messages = []

    if total == 1:
        options = [
            "Ты отметила свою первую радость. Очень мягкое и важное начало.",
            "Первая запись есть — уже не ноль. Дальше можно очень по чуть-чуть.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif total == 7:
        options = [
            "У тебя уже целая неделя с отмеченными радостями. Это хорошая привычка.",
            "Семь разных моментов, о которых можно себе напомнить. Звучит тепло.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif total == 30:
        options = [
            "У тебя уже много сохранённых приятных моментов. Это целая личная история.",
            "Ты собрала заметную коллекцию радостей. Они уже не теряются в памяти.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))

    if streak == 7:
        options = [
            "Неделю подряд ты каждый день находишь что-то хорошее. Это серьёзная забота о себе.",
            "Семь дней подряд ты не забывала о своих маленьких радостях. Это важно.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))
    elif streak == 30:
        options = [
            "Целый месяц ты даёшь себе внимание каждый день. Это очень сильное движение к себе.",
        ]
        messages.append(add_emoji_prefix(random.choice(options)))

    for m in messages:
        send_message(chat_id, m)


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
            "Можно начать с одной небольшой, когда появится хоть немного ресурса.",
        )
        return

    first_str = first_date.strftime("%d.%m.%Y") if first_date else "—"

    msg = (
        f"{em} Небольшая сводка:\n\n"
        f"• У тебя уже есть своя коллекция приятных моментов.\n"
        f"• За последние 7 дней радости всё равно продолжали появляться.\n"
        f"• У тебя есть серия дней, где ты не забываешь про себя: сейчас стрик — {streak}.\n"
        f"• Первая запись была: {first_str}.\n\n"
        "Каждая маленькая радость — это твой личный шаг к более тёплому отношению к себе."
    )
    send_message(chat_id, msg)


# --------------------------
# Письмо себе в будущее
# --------------------------

def handle_letter_command(chat_id: int):
    clear_dialog_state(chat_id)
    send_message(
        chat_id,
        add_emoji_prefix(
            "Давай устроим маленькое письмо в будущее.\n\n"
            "Выбери, когда хочешь его получить:\n"
            "• 7 — через неделю\n"
            "• 14 — через две недели\n"
            "• 30 — через месяц\n\n"
            "Просто напиши цифру: 7, 14 или 30.\n"
            "Если передумаешь — напиши /cancel или «отмена»."
        )
    )
    set_dialog_state(chat_id, "await_letter_period", None)


def handle_letter_period(chat_id: int, text: str):
    if is_cancel_message(text):
        clear_dialog_state(chat_id)
        send_message(
            chat_id,
            add_emoji_prefix(
                "Хорошо, отложим письмо в будущее. Если захочешь вернуться — просто напиши /letter."
            )
        )
        return

    norm = normalize_text_for_match(text)
    if norm not in ["7", "14", "30"]:
        send_message(
            chat_id,
            add_emoji_prefix(
                "Не совсем поняла срок.\n"
                "Напиши, пожалуйста, только цифру: 7, 14 или 30.\n"
                "Если передумаешь — можешь написать /cancel."
            )
        )
        return
    days = int(norm)
    set_dialog_state(chat_id, "await_letter_text", {"days": days})
    send_message(
        chat_id,
        add_emoji_prefix(
            "Хорошо. Напиши сейчас письмо себе — той, которая будет читать его через этот срок.\n\n"
            "Можно рассказать, как ты себя чувствуешь сейчас, что тебе важно, о чём мечтаешь или что хочешь себе напомнить.\n"
            "Если передумаешь — напиши /cancel или «отмена»."
        )
    )


def handle_letter_text(chat_id: int, text: str, meta: dict):
    if is_cancel_message(text):
        clear_dialog_state(chat_id)
        send_message(
            chat_id,
            add_emoji_prefix(
                "Окей, без письма сейчас. Если захочешь вернуться к этой идее — просто вызови /letter ещё раз."
            )
        )
        return

    days = meta.get("days", 7)
    cleaned = text.strip()
    if not cleaned:
        send_message(
            chat_id,
            add_emoji_prefix(
                "Похоже, письмо получилось пустым.\n"
                "Попробуй написать хотя бы пару строк для себя из будущего. Или напиши /cancel, если пока не хочется."
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
# Недельный и месячный обзоры
# --------------------------

def send_weekly_human_summary(chat_id: int):
    today_local = datetime.now().date()
    start = today_local - timedelta(days=6)
    joys = get_joys_between(chat_id, start, today_local)

    # фильтруем нейтральные и странные записи
    filtered = []
    for created_at, text in joys:
        if not text.strip():
            continue
        if is_no_joy_message(text):
            continue
        norm = normalize_text_for_match(text)
        if any(star_seq in text for star_seq in ["***", "****"]):
            continue
        filtered.append((created_at, text))

    if not filtered:
        send_message(
            chat_id,
            add_emoji_prefix(
                "На этой неделе у меня почти нет твоих радостей.\n"
                "Если дашь себе шанс, в следующую можно попробовать находить хотя бы одну маленькую опору в день."
            )
        )
        return

    theme_counts: Dict[str, int] = {k: 0 for k in THEME_KEYWORDS.keys()}
    for _, text in filtered:
        themes = classify_joy_themes(text)
        for t in themes:
            theme_counts[t] += 1

    themes_phrase = summarize_themes(theme_counts)

    lines = []
    for created_at, text in filtered:
        try:
            dt = datetime.fromisoformat(created_at)
            date_str = dt.strftime("%d.%m")
        except Exception:
            date_str = created_at[:10]
        emo = random.choice(JOY_EMOJIS)
        lines.append(f"{emo} {date_str} — {text}")

    header = "Собрала для тебя маленький обзор недели — вот хорошие моменты, которые были рядом с тобой:"
    body = "\n".join(lines)

    if themes_phrase:
        extra = (
            f"\n\nЕсли коротко, на этой неделе {themes_phrase} "
            "Это хороший ориентир, на что ты сейчас опираешься."
        )
    else:
        extra = ""

    send_message(chat_id, f"{header}\n\n{body}{extra}")


def send_monthly_human_summary(chat_id: int):
    today_local = datetime.now().date()
    first_this_month = today_local.replace(day=1)
    end_prev = first_this_month - timedelta(days=1)
    start_prev = end_prev.replace(day=1)

    joys = get_joys_between(chat_id, start_prev, end_prev)

    filtered = []
    for created_at, text in joys:
        if not text.strip():
            continue
        if is_no_joy_message(text):
            continue
        if any(star_seq in text for star_seq in ["***", "****"]):
            continue
        filtered.append((created_at, text))

    if not filtered:
        send_message(
            chat_id,
            add_emoji_prefix(
                "За прошлый месяц у меня почти нет твоих записей.\n"
                "Если захочешь, этот месяц может стать началом более тёплой и внимательной истории с собой."
            )
        )
        return

    theme_counts: Dict[str, int] = {k: 0 for k in THEME_KEYWORDS.keys()}
    for _, text in filtered:
        themes = classify_joy_themes(text)
        for t in themes:
            theme_counts[t] += 1

    themes_phrase = summarize_themes(theme_counts)

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
            f"За этот месяц у тебя накопилось немало тёплых моментов. "
            f"Если смотреть на всё вместе, видно, что {themes_phrase}"
        )
    else:
        intro = (
            f"{header}\n\n"
            "В этом месяце у тебя было много разных дней, но ты всё равно находила пространство для маленьких радостей. "
            "Это очень бережно по отношению к себе."
        )

    send_message(chat_id, add_emoji_prefix(intro))


# --------------------------
# Дневной отчёт
# --------------------------

def send_daily_report_for_user(chat_id: int):
    today_local = datetime.now().date()
    joys = get_joys_for_date(chat_id, today_local)

    filtered = []
    for created_at, text in joys:
        if not text.strip():
            continue
        if is_no_joy_message(text):
            continue
        if any(star_seq in text for star_seq in ["***", "****"]):
            continue
        filtered.append((created_at, text))

    if not filtered:
        send_message(
            chat_id,
            add_emoji_prefix(
                "Сегодня у меня нет записанных радостей.\n"
                "Похоже, день был непростым. Давай просто отметим, что ты его пережила. "
                "А завтра можно поискать хотя бы один маленький тёплый момент."
            )
        )
        return

    lines = []
    for created_at, text in filtered:
        try:
            dt = datetime.fromisoformat(created_at)
            time_str = dt.strftime("%H:%M")
        except Exception:
            time_str = created_at[11:16]
        emo = random.choice(JOY_EMOJIS)
        lines.append(f"{emo} {time_str} — {text}")

    header = "Посмотрим, что хорошего ты успела заметить в этом дне:"
    body = "\n".join(lines)
    send_message(chat_id, f"{header}\n\n{body}")


# --------------------------
# Напоминания и раннеры
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

        # напоминание в 18:00
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
                                "Давай не дадим ему потеряться — напиши мне о нём.",
                            )
                    except Exception as e:
                        print(f"Error sending daily reminder to {user_id}:", e)
                reminded_dates.add(today)

        time.sleep(60)


def daily_report_runner():
    print("Daily report runner started.")
    reported_dates = set()

    while True:
        now = datetime.now()
        today = now.date()

        for d in list(reported_dates):
            if d != today:
                reported_dates.remove(d)

        # отчёт в 21:00
        if now.hour == 21 and now.minute == 0:
            if today not in reported_dates:
                print("Sending daily reports...")
                for user_id in get_all_user_ids():
                    try:
                        send_daily_report_for_user(user_id)
                    except Exception as e:
                        print(f"Error sending daily report to {user_id}:", e)
                reported_dates.add(today)

        time.sleep(60)


def weekly_summary_runner():
    print("Weekly summary runner started.")
    sent_weeks = set()

    while True:
        now = datetime.now()
        today = now.date()
        year, week_num, _ = today.isocalendar()
        key = (year, week_num)

        for k in list(sent_weeks):
            if k[0] != year or k[1] != week_num:
                sent_weeks.remove(k)

        # воскресенье 22:15
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
    print("Monthly summary runner started.")
    sent_months = set()

    while True:
        now = datetime.now()
        today = now.date()
        ym = (today.year, today.month)

        for k in list(sent_months):
            if k != ym:
                sent_months.remove(k)

        # 1-е число месяца, 20:00
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


def future_letters_runner():
    print("Future letters runner started.")
    while True:
        try:
            letters = get_due_letters()
            if letters:
                print(f"Sending {len(letters)} future letters...")
            for letter_id, chat_id, text, send_at, created_at in letters:
                try:
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
# Обработка сообщений
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
        send_message(
            chat_id,
            add_emoji_prefix(
                "Хорошо, остановимся. Можно просто продолжить писать сюда радости, когда почувствуешь желание."
            )
        )
        return

    # Команды
    if stripped.startswith("/start"):
        clear_dialog_state(chat_id)
        send_message(
            chat_id,
            add_emoji_prefix(
                "Привет. Я твой дневник маленьких радостей.\n\n"
                "Каждый день ты можешь писать сюда хоть одну крошечную приятную вещь: "
                "вкусный кофе, встречу, удавшийся день, тёплый плед или пару свободных минут.\n\n"
                "В 18:00 я напомню, если ты сегодня ничего не написала.\n"
                "В 21:00 — пришлю небольшой отчёт о хорошем, которое мы успели заметить."
            )
        )
        return

    if stripped.startswith("/stats"):
        send_stats(chat_id)
        return

    if stripped.startswith("/letter"):
        handle_letter_command(chat_id)
        return

    # проверяем, есть ли активный диалог
    state, meta = get_dialog_state(chat_id)

    if state == "await_letter_period":
        handle_letter_period(chat_id, text)
        return

    if state == "await_letter_text":
        handle_letter_text(chat_id, text, meta or {})
        return

    # сначала проверяем мат на исходном тексте
    if contains_profanity(stripped):
        send_message(
            chat_id,
            add_emoji_prefix(
                "Вижу, что эмоций много и слова получились крепкими.\n"
                "Если захочешь, можем попробовать описать это состояние чуть мягче — так тебе будет легче к этому возвращаться потом."
            )
        )
        # не записываем это как радость
        return

    cleaned = clean_text_pipeline(text)
    if not cleaned:
        send_message(
            chat_id,
            "Мне не удалось ничего сохранить.\n"
            "Попробуй написать чуть конкретнее, что тебя сегодня порадовало.",
        )
        return

    # приветствия — отвечаем, но НЕ записываем как радость
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
        return

    # тревога
    if is_anxiety_message(cleaned):
        send_message(chat_id, get_anxiety_response())
        add_sad_event(chat_id)
        return

    # усталость
    if is_tired_message(cleaned):
        send_message(chat_id, get_tired_response())
        add_sad_event(chat_id)
        return

    # грусть
    if is_sad_message(cleaned):
        send_message(chat_id, get_sad_response())
        add_sad_event(chat_id)
        return

    # нейтральные «не знаю, что написать»
    if is_no_joy_message(cleaned):
        send_message(chat_id, get_no_joy_response())
        return

    # обычная радость
    add_joy(chat_id, cleaned)
    send_message(chat_id, get_joy_response(chat_id))
    check_and_send_achievements(chat_id)


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
