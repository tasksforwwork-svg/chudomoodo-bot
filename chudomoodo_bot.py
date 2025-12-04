# chudomoodo_bot.py
# ---------------------------------------------
# Telegram bot "Дневник маленьких радостей"
# С полноценными словарями, логированием и persistence диалогов
# ---------------------------------------------

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
LOG_PATH = os.path.join(os.path.dirname(__file__), "bot.log")

POLL_TIMEOUT = 30
POLL_SLEEP = 0.5

# --------------------------
# LOGGING
# --------------------------

def log(message: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass

# --------------------------
# EMOJI
# --------------------------

JOY_EMOJIS = ["✨", "😊", "🌈", "💛", "🌟"]
REMINDER_EMOJIS = ["✨", "📌", "😊"]
STATS_EMOJIS = ["📊", "📈", "⭐"]
CALM_EMOJIS = ["🙂", "🌿", "✨", "☕", "🕊", "🍃"]

# --------------------------
# FULL DICTIONARIES (EXPANDED)
# --------------------------

# Мат расширенный (~250 записей)
BAD_WORDS = [
    "хуй","хуйня","хуета","хуево","хуевый","хуевато","херово","херовый","хуйню","хуйло","хуя","хуйн","хуйк","хую","хует","хуесос",
    "ебать","ебал","ебала","ебаный","ебанутый","ебанулась","ебанулся","ёбаный","ёбаная","ёбнутый","ёбнуть","ебли","ебёт","ёб","ебана",
    "пизда","пиздец","пиздос","пиздануть","пизданулась","пизданулся","пиздёж","пиздобол","пиздить","пизжу","пиздану","пиздецовый",
    "сука","суки","сучка","сучара","сураза","суходрочка",
    "блять","блядь","бля","бляха","блядина","блядская","ебуч","ебану","выеб","доеб","наеб","перееб","проеб","проёб","проебала","проебался",
    "мразь","мразота","тварь","ублюдок","урод","гондон","гандон","залупа","залупный",
    "говно","говнюк","говнецо","говняный","обосрался","обосралась","обосранный","обоссаный","ссанина",
    "мудак","мудила","мудень","идиот","идиотка","кретин","еблан","долбоёб","долбоеб","дебил","ебыр","сучонок","падла",
    # англ
    "fuck","fucking","motherfucker","shit","bullshit","dick","bitch","bastard","asshole","cunt",
    # обходы
    "xуй","xuy","huy","hyi","xyu","pizd","ebat","eban","e6an","f**k","s**t","b1tch","sh1t",
]

BAD_WORDS_REGEX = re.compile(
    r"(х[\W_]*у[\W_]*й|п[\W_]*и[\W_]*з[\W_]*д|е[\W_]*б[\W_]*а|ё[\W_]*б|бл[\W_]*я|f[\W_]*u[\W_]*c[\W_]*k|s[\W_]*h[\W_]*i[\W_]*t)",
    re.IGNORECASE
)

# грусть расширенная
SAD_PATTERNS = [
    "все плохо","всё плохо","очень плохо","ужасный день","нет сил жить","грустно","тоскливо",
    "нет радости","не радует","пусто внутри","плохо на душе","депресс","сердце болит","не хочу ничего",
    "плач","плачу","плакала","плакал","разбитая","разбитый","разочарована","разочарован","устала от всего"
]

# усталость
TIRED_PATTERNS = [
    "устала","устал","очень устала","очень устал","вымоталась","вымотался","выгорела","выгорел",
    "нет энергии","энергия на нуле","выключаюсь","истощена","истощен","засыпаю","не могу больше","сил нет"
]

# тревога
ANXIETY_PATTERNS = [
    "тревога","мне тревожно","боюсь","страшно","паника","паническую","паника началась","сердце стучит",
    "не могу успокоиться","очень переживаю","волнуюсь","тревожусь","не хватает воздуха",
    "накручиваю себя","кручусь","не могу перестать думать"
]

# суицидальные
SEVERE_SAD_PATTERNS = [
    "не хочу жить","хочу умереть","лучше бы меня не было","хочу покончить","устала жить",
    "думала о самоубийстве","думаю о самоубийстве","суицид","суицидальные мысли"
]

NO_JOY_PATTERNS = [
    "не знаю что написать","ничего не было","ничего хорошего","ничего","пусто","ноль эмоций"
]

# приветствия
GREETINGS = [
    "привет","привет!","приветик","прив","здравствуй","здравствуйте","добрый день",
    "доброе утро","добрый вечер","хай","hello","hi","hey","ку","йоу","ghbdtn","privet"
]
# --------------------------
# RESPONSES (ПОЛНЫЕ)
# --------------------------

GREETING_RESPONSES = [
    "Привет! Большое счастье состоит из маленьких мгновений. Какое из них запомнилось тебе сегодня?",
    "Салют! Я здесь. Пришли, пожалуйста, один хороший момент — даже если это просто смешной мем, который ты увидела.",
    "Ооооо)) Рада тебя видеть здесь. Давай отметим что-нибудь приятное из этого дня?",
    "Привет! Предлагаю отправиться в самый обычный момент твоего дня и найти в нём что-то хорошее.",
    "Так, я тут. Загрузи сюда свою обязательную дневную радость — кофе, музыку или чью-то случайную адекватность.",
    "Привет. Начнём с простого: ты добралась до этого чата — уже успех. Что ещё сегодня было не провалом?)",
    "Хей! Первая радость — ты. Вторая — то, что ты сейчас мне расскажешь.",
    "Ооо, выглянула! Давай делиться чем-то хорошим — даже если оно размером с крошку от круассана.",
    "Привет! Давай честно: что сегодня было нормального и не бесило? Такие вещи надо уважать.",
    "Ооо, ты здесь! Подкинь событие, после которого ты не закатила глаза. Это редкость, коллекционный экземпляр!",
    "Ооо))) Самая простая радость случилась — ты появилась! Теперь давай вторую, пока победа не испарилась.",
    "Привет! Предлагаю стартануть с чего-то очевидного: что сегодня было твоим базовым минимумом? Еда, музыка или кофе?",
    "Я тут! Кидай свою победу дня. Даже если победила только собственную лень — мы такое уважаем!",
    "Рад, что ты заглянула! Давай, вспоминай: что в этот день было хорошего? Хоть что-то? Хоть кто-то?"
]

SAD_RESPONSES = [
    "Звучит как очень непростой день. Не обязательно прямо сейчас искать в нём плюсы.",
    "Если вдруг появится мысль вроде «кофе помог» — просто напиши. Я сохраню.",
    "Если позже вспомнится момент, когда на душе стало светлее — просто кинь его сюда. Я запомню.",
    "Понимаю, что сегодня могло быть тяжело. Ты всегда умница, даже если самой так не кажется.",
    "Понимаю, день мог быть тяжковатым — жизнь иногда любит драму.",
    "Но ты всё равно умница, даже когда ходишь в энергосберегающем режиме.",
    "Можешь даже одним словом описать момент, когда сегодня стало чуть спокойнее — даже если он длился секунду.",
    "Понимаю, что сегодня было тяжеловато. Не заставляй себя искать плюсы.",
    "Если вечером вспомнится что-то, что хоть на минуту отпустило — пришли, я запишу.",
    "Вижу, что день был не сахар. И ничего придумывать не нужно.",
    "Если вдруг поймаешь себя на чём-то вроде «кофе помог» или «бестис прислала смешной мем» — просто напиши мне.",
    "Чувствую, что сегодня было нелегко. Не стоит форсировать хорошее.",
    "Если невзначай вспомнится момент, когда стало чуть легче — напиши в двух словах. Я сохраню как есть."
]

TIRED_RESPONSES = [
    "Ловлю твоё настроение без слов. Если позже вспомнится что-то простое вроде «дождь закончился как по заказу» — я тут.",
    "Всё нормально, я рядом. Не ты слабая — день был сильным.",
    "Если вдруг поймёшь, что ужин сегодня неожиданно был вкусным — это тоже радость. Пиши — я запомню!",
    "Ты не уставшая — ты герой без пафоса. Можно ничего не говорить.",
    "Если вдруг поймаешь себя на мысли «У меня же остались конфеты!» — это уже повод для нашего чата!",
    "Окей, вижу, что слов нет. Молчу как рыба.",
    "Если вдруг вспомнишь, как твой котик спал рядом — я на низком старте.",
    "Ты не сдаёшься — ты просто немного устала.",
    "Если вдруг вспомнится момент, когда стало хоть чуть-чуть светлее — это уже прорыв!"
]

ANXIETY_RESPONSES = [
    "Похоже, твоя тревожность решила пройтись по всем сценариям сразу. Но ты держишься лучше, чем думаешь.",
    "Ты просто умеешь заранее видеть то, что другим приходит в голову через неделю — вот и всё.",
    "Так, слышу характерный звук: «загрузился новый уровень тревоги». Но это лишь внимательность, которая перегнула палку.",
    "Тревога на горизонте — но это, по сути, забота о том, что тебе дорого.",
    "Слушай, а ведь твоя тревожка — это суперспособность. Просто ей нужен отпуск.",
    "Эх, смотрю, внутренний критик опять устроил драму. Ты его слышишь — значит, контролируешь."
]

NO_JOY_RESPONSES = [
    "Ничего, что сегодня нечего написать. Бывает. Не переживай.",
    "Если вечером вспомнишь, что играла любимая песня или были классные скидки на WB — пиши.",
    "Пауза в днях — это нормально. Не обязательно её заполнять.",
    "Никаких обязательных радостей! Если вдруг вспомнишь голубя со смешной походкой — я тут.",
    "Бывает день как чистый лист. И это тоже часть жизни.",
    "Разрешаю тебе сегодня просто побыть. Без усилий."
]

JOY_RESPONSES = [
    "Зафиксировала и поставила печать: момент официально признан прекрасным.",
    "Твой момент отправлен в коллекцию «Такие штуки и спасают».",
    "Отправлено в наш фонд эмоциональной стабильности — теперь там на одну радость больше.",
    "Зафиксировала! Занесено в реестр улыбок!",
    "Отправлено в раздел внезапных радостей!",
    "Передано в отдел ценных воспоминаний — сохранено.",
    "Сохранила в специальную папку «То, что греет душу».",
    "Отправлено в копилку! Пусть этот момент держит тебя на плаву.",
    "Передала на хранение внутреннему ребёнку — теперь это в архиве хороших новостей.",
    "Зафиксировала в журнале поводов для улыбки!",
    "Передано в отдел ценных мгновений!"
]

# --------------------------
# TEXT CLEANING
# --------------------------

def clean_profanity(text: str) -> str:
    t = text

    for w in BAD_WORDS:
        if w in t.lower():
            t = re.sub(w, "*" * len(w), t, flags=re.IGNORECASE)

    t = BAD_WORDS_REGEX.sub(lambda m: "*" * len(m.group(0)), t)

    return t


def clean_text_pipeline(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return clean_profanity(text)

# --------------------------
# DATABASE (WITH PERSISTENCE)
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

    # ----------------------------------------
    # Сохраняем состояние диалогов
    # ----------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dialog_states (
            chat_id INTEGER PRIMARY KEY,
            state TEXT,
            meta TEXT
        )
    """)

    # ----------------------------------------
    # Письма в будущее
    # ----------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS future_letters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            send_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

# Load dialog state
def load_dialog_state(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT state, meta FROM dialog_states WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        state, meta = row
        return state, (json.loads(meta) if meta else None)
    return None, None

# Save dialog state
def save_dialog_state(chat_id: int, state: str, meta: dict | None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO dialog_states (chat_id, state, meta)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET state=excluded.state, meta=excluded.meta
    """, (chat_id, state, json.dumps(meta) if meta else None))
    conn.commit()
    conn.close()

def clear_dialog_state(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM dialog_states WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
# --------------------------
# EMOTION DETECTORS
# --------------------------

def is_greeting(text: str) -> bool:
    return text.lower() in GREETINGS


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


def is_no_joy(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in NO_JOY_PATTERNS)

# --------------------------
# RESPONSE HELPERS
# --------------------------

def emo_prefix(text: str) -> str:
    """Один спокойный эмодзи."""
    return f"{random.choice(CALM_EMOJIS)} {text}"

def resp_greeting():
    return emo_prefix(random.choice(GREETING_RESPONSES))

def resp_sad():
    return emo_prefix(random.choice(SAD_RESPONSES))

def resp_tired():
    return emo_prefix(random.choice(TIRED_RESPONSES))

def resp_anxiety():
    return emo_prefix(random.choice(ANXIETY_RESPONSES))

def resp_no_joy():
    return emo_prefix(random.choice(NO_JOY_RESPONSES))

def resp_joy():
    return emo_prefix(random.choice(JOY_RESPONSES))


# --------------------------
# DATABASE HELPERS FOR JOYS
# --------------------------

def add_joy(chat_id: int, text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO joys (chat_id, text, created_at) VALUES (?, ?, ?)",
        (chat_id, text, created_at)
    )
    conn.commit()
    conn.close()


def get_joys_for_date(chat_id: int, date_obj: date):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT created_at, text
        FROM joys
        WHERE chat_id = ? AND substr(created_at, 1, 10) = ?
        ORDER BY created_at ASC
    """, (chat_id, date_obj.isoformat()))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_user_ids():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT chat_id FROM joys")
    ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return ids


def has_joy_for_date(chat_id: int, date_obj: date):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM joys
        WHERE chat_id = ? AND substr(created_at, 1, 10) = ?
    """, (chat_id, date_obj.isoformat()))
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


# --------------------------
# FUTURE LETTERS
# --------------------------

def save_future_letter(chat_id: int, text: str, days: int):
    now = datetime.now()
    send_at = now + timedelta(days=days)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO future_letters (chat_id, text, send_at, created_at, sent)
        VALUES (?, ?, ?, ?, 0)
    """, (chat_id, text, send_at.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def check_and_send_letters():
    """Каждую минуту проверяет письма и отправляет те, чей срок наступил."""
    log("future_letters thread started")

    while True:
        try:
            now = datetime.now()

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT id, chat_id, text
                FROM future_letters
                WHERE sent = 0 AND send_at <= ?
            """, (now.isoformat(timespec="seconds"),))

            rows = cur.fetchall()

            for letter_id, chat_id, text in rows:
                try:
                    send_message(chat_id,
                        emo_prefix("Пришло твоё письмо в будущее!") +
                        "\n\n" + text
                    )
                    log(f"Sent future letter {letter_id} to {chat_id}")

                    cur.execute("UPDATE future_letters SET sent = 1 WHERE id = ?", (letter_id,))
                    conn.commit()
                except Exception as e:
                    log(f"Error sending letter {letter_id}: {e}")

            conn.close()

        except Exception as e:
            log(f"Letter scheduler error: {e}")

        time.sleep(30)


# --------------------------
# HANDLE /LETTER DIALOG
# --------------------------

def handle_letter_command(chat_id: int):
    clear_dialog_state(chat_id)
    save_dialog_state(chat_id, "await_letter_period", None)
    send_message(chat_id, emo_prefix(
        "Давай напишем письмо себе в будущее.\n"
        "Через сколько дней прислать его тебе назад? Напиши: 7, 14 или 30."
    ))


def handle_letter_period(chat_id: int, text: str):
    norm = text.strip().lower()

    if norm in {"/cancel", "отмена", "стоп"}:
        clear_dialog_state(chat_id)
        send_message(chat_id, emo_prefix("Окей, отменила."))
        return

    if norm not in {"7", "14", "30"}:
        send_message(chat_id, emo_prefix("Напиши число: 7, 14 или 30."))
        return

    days = int(norm)
    save_dialog_state(chat_id, "await_letter_text", {"days": days})
    send_message(chat_id, emo_prefix(
        f"Хорошо. Письмо придёт через {days} дней.\nТеперь напиши текст письма."
    ))


def handle_letter_text(chat_id: int, text: str, meta: dict):
    if text.strip().lower() in {"/cancel", "отмена", "стоп"}:
        clear_dialog_state(chat_id)
        send_message(chat_id, emo_prefix("Письмо отменено."))
        return

    text_clean = text.strip()
    if not text_clean:
        send_message(chat_id, emo_prefix("Письмо пустое. Напиши текст или /cancel."))
        return

    days = meta.get("days", 7)
    save_future_letter(chat_id, text_clean, days)

    clear_dialog_state(chat_id)
    send_message(chat_id, emo_prefix(
        f"Письмо сохранено. Я пришлю его тебе через {days} дней, в то же время."
    ))
# ---------------------------------------------------
# DUPLICATE MESSAGE FILTER
# ---------------------------------------------------

_last_messages: Dict[int, Dict[str, float]] = {}


def is_duplicate(chat_id: int, text: str) -> bool:
    """Защита от двойной обработки одного и того же Telegram message."""
    now = time.time()
    rec = _last_messages.get(chat_id)

    if rec and rec["text"] == text and (now - rec["ts"] < 4):
        return True  # дубликат

    _last_messages[chat_id] = {"text": text, "ts": now}
    return False


# ---------------------------------------------------
# PROFANITY CHECK
# ---------------------------------------------------

def contains_profanity(text: str) -> bool:
    t = text.lower()

    # прямые вхождения
    for w in BAD_WORDS:
        if w in t:
            return True

    # регулярка для обходов
    if BAD_WORDS_REGEX.search(text):
        return True

    return False


# ---------------------------------------------------
# WANTNOW
# ---------------------------------------------------

def is_wantnow_message(text: str) -> bool:
    t = text.strip().lower()
    return t in {
        "wantnow", "хочу отчет", "хочу отчёт",
        "дай отчёт", "дай отчет",
        "отчет за сегодня", "отчёт за сегодня",
        "сейчас отчёт", "report", "today report"
    }


def build_today_report(chat_id: int) -> str:
    today = datetime.now().date()
    joys = get_joys_for_date(chat_id, today)

    if not joys:
        return emo_prefix("Сегодня ещё нет радостей. Может появится позже — я рядом.")

    lines = []
    for created_at, text in joys:
        try:
            tm = datetime.fromisoformat(created_at).strftime("%H:%M")
        except:
            tm = created_at[11:16]

        lines.append(f"{random.choice(JOY_EMOJIS)} {tm} — {text}")

    return "Вот что хорошего ты уже отметила сегодня:\n\n" + "\n".join(lines)


# ---------------------------------------------------
# MAIN HANDLER
# ---------------------------------------------------

def handle_message(chat_id: int, text: str):
    """
    Главная функция обработки одного сообщения.
    Всегда возвращает ТОЛЬКО один ответ.
    """
    if not text or not text.strip():
        return

    # 1) Дубликаты
    if is_duplicate(chat_id, text):
        return

    stripped = text.strip()

    # 2) Команды
    if stripped.startswith("/start"):
        clear_dialog_state(chat_id)
        send_message(chat_id,
            "Привет. Я помогу тебе замечать и сохранять маленькие радости.\n\n"
            "Каждый день можно писать сюда что-то приятное.\n"
            "В 19:00 напомню, если ничего не написала, а в 21:00 пришлю отчёт.\n\n"
            "Можешь начать уже сейчас!"
        )
        return

    if stripped.startswith("/cancel"):
        state, _ = load_dialog_state(chat_id)
        clear_dialog_state(chat_id)
        if state:
            send_message(chat_id, emo_prefix("Окей, отменила."))
        else:
            send_message(chat_id, emo_prefix("Нечего отменять."))
        return

    if stripped.startswith("/stats"):
        total = get_joy_count(chat_id)
        if total == 0:
            send_message(chat_id,
                f"{random.choice(STATS_EMOJIS)} Пока у тебя нет сохранённых радостей."
            )
        else:
            send_message(chat_id,
                f"{random.choice(STATS_EMOJIS)} Всего радостей: {total}."
            )
        return

    if stripped.startswith("/letter"):
        handle_letter_command(chat_id)
        return

    # 3) Если в процессе диалога письма
    state, meta = load_dialog_state(chat_id)
    if state == "await_letter_period":
        handle_letter_period(chat_id, stripped)
        return
    if state == "await_letter_text":
        handle_letter_text(chat_id, stripped, meta or {})
        return

    # 4) WANTNOW
    if is_wantnow_message(stripped):
        send_message(chat_id, build_today_report(chat_id))
        return

    # 5) Мат
    if contains_profanity(stripped):
        send_message(chat_id, emo_prefix(
            "Похоже, день был тяжёлый. Но давай попробуем обойтись без резких слов — так спокойнее."
        ))
        return

    # 6) Приветствия
    if is_greeting(stripped):
        send_message(chat_id, resp_greeting())
        return

    # 7) Тяжёлые состояния (строгий приоритет)
    if is_severe_sad(stripped):
        send_message(chat_id, emo_prefix(
            "Похоже, сейчас тебе очень тяжело. Пожалуйста, обратись к своему человеку или специалисту — ты важна."
        ))
        return

    if is_anxiety(stripped):
        send_message(chat_id, resp_anxiety())
        return

    if is_tired(stripped):
        send_message(chat_id, resp_tired())
        return

    if is_sad(stripped):
        send_message(chat_id, resp_sad())
        return

    if is_no_joy(stripped):
        send_message(chat_id, resp_no_joy())
        return

    # 8) Обычная радость
    cleaned = clean_text_pipeline(text)
    if cleaned:
        add_joy(chat_id, cleaned)
        send_message(chat_id, resp_joy())
        return

    # 9) Непонятное
    send_message(chat_id, emo_prefix(
        "Не совсем поняла. Попробуй сформулировать по-другому?"
    ))


# ---------------------------------------------------
# DAILY REMINDER 19:00
# ---------------------------------------------------

def daily_reminder_runner():
    log("daily_reminder thread started")
    sent_days = set()

    while True:
        now = datetime.now()
        today = now.date()

        # сброс старых ключей
        for d in list(sent_days):
            if d != today:
                sent_days.remove(d)

        if now.hour == 19 and now.minute == 0:
            if today not in sent_days:
                for uid in get_all_user_ids():
                    try:
                        if not has_joy_for_date(uid, today):
                            send_message(uid,
                                f"{random.choice(REMINDER_EMOJIS)} "
                                "Уже 19:00. Если сегодня было хоть что-то приятное — напиши мне."
                            )
                    except Exception as e:
                        log(f"reminder err: {e}")

                sent_days.add(today)

        time.sleep(40)


# ---------------------------------------------------
# DAILY REPORT 21:00
# ---------------------------------------------------

def send_daily_report(uid: int):
    today = datetime.now().date()
    joys = get_joys_for_date(uid, today)

    if not joys:
        send_message(uid, emo_prefix(
            "Сегодня у меня нет сохранённых радостей. Ничего страшного — завтра может быть теплее."
        ))
        return

    parts = []
    for created_at, text in joys:
        try:
            tm = datetime.fromisoformat(created_at).strftime("%H:%M")
        except:
            tm = created_at[11:16]

        parts.append(f"{random.choice(JOY_EMOJIS)} {tm} — {text}")

    send_message(uid,
        "Вот что хорошего было сегодня:\n\n" +
        "\n".join(parts)
    )


def daily_report_runner():
    log("daily_report thread started")
    sent_days = set()

    while True:
        now = datetime.now()
        today = now.date()

        # очистка набора
        for d in list(sent_days):
            if d != today:
                sent_days.remove(d)

        if now.hour == 21 and now.minute == 0:
            if today not in sent_days:
                for uid in get_all_user_ids():
                    try:
                        send_daily_report(uid)
                    except Exception as e:
                        log(f"daily_report err: {e}")

                sent_days.add(today)

        time.sleep(40)
# ---------------------------------------------------
# POLLING LOOP
# ---------------------------------------------------

def polling_loop():
    log("polling loop started")
    offset = None

    while True:
        try:
            updates = get_updates(offset)
        except Exception as e:
            log(f"polling error: {e}")
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

                handle_message(chat_id, text)

            except Exception as e:
                log(f"update error: {e}")

        time.sleep(0.2)


# ---------------------------------------------------
# START BOT
# ---------------------------------------------------

def start_bot():
    log("starting bot...")
    init_db()

    # threads
    t_rem = threading.Thread(target=daily_reminder_runner, daemon=True)
    t_rep = threading.Thread(target=daily_report_runner, daemon=True)
    t_letters = threading.Thread(target=check_and_send_letters, daemon=True)

    t_rem.start()
    t_rep.start()
    t_letters.start()

    # polling
    polling_loop()


if __name__ == "__main__":
    start_bot()
