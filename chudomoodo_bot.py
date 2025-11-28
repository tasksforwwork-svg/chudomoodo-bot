import logging
import os
import json
import random
from datetime import datetime, date, time, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Списки слов для анализа тональности сообщений (пример, расширяемые)
SAD_PATTERNS = ["грусть", "печаль", "плачу", "скучаю", "одинок", "тоска", "обидно", "грустно"]
TIRED_PATTERNS = ["устал", "сонливость", "упал", "надрыв", "раздражен", "устала", "надоел"]
ANXIETY_PATTERNS = ["беспокойство", "волнение", "тревог", "нервничаю", "паника", "паническое"]
GREETING_PATTERNS = ["привет", "здравствуй", "добрый", "прив", "приветствую", "хай", "доброго"]
SEVERE_SAD_PATTERNS = ["ничего не хочу", "убит", "смерть", "отчаяние", "депресс", "безнадеж", "надоело жить", "раздавлен"]
NO_JOY_PATTERNS = ["ни радости", "никакой радости", "не весел", "ничего хорошего", "нет сил"]
BAD_WORDS = ["бля", "сука", "хуй", "пизд", "еба"]

GREETING_RESPONSES = [
    "Привет! 😊 Как твои дела?",
    "Здравствуй! Рад тебя видеть! 🌟",
    "Хай! Как проходит твой день?",
    "Привет-привет! Чем могу порадовать тебя сегодня?",
    "Доброго времени суток! Рассказывай, что нового.",
    "Привет! Я слушаю тебя.",
    "Приветики! Что у тебя на душе?",
    "Рад видеть тебя! Чем могу помочь?",
    "Привет! Как настроение?",
    "Салют! Что интересного происходит?"
    # + дополнительные фразы
]
JOY_ACCEPTANCE_RESPONSES = [
    "Здорово! Я очень рад за тебя! 🎉",
    "Как замечательно! Пусть это чувство радости всегда с тобой.",
    "Прекрасно! Делись ещё такими радостными моментами! 😊",
    "Ура! Очень рад за тебя! Поделись ещё, если хочешь.",
    "Это здорово! Я люблю слышать хорошие новости.",
    "Радуюсь вместе с тобой! Продолжай радовать себя и меня.",
    "Молодец! Очень вдохновляет. 😊",
    "Супер! Продолжай в том же духе.",
    "Как здорово! Спасибо, что поделился этой радостью.",
    "Великолепно! Будем праздновать это душевно."
    # до 100 фраз можно дополнить
]

CHOOSE_PERIOD, WRITE_LETTER = range(2)
DATA_FILE = 'data.json'

def load_data():
    """Загрузка данных или инициализация структуры."""
    if not os.path.exists(DATA_FILE):
        data = {"joys": {}, "memory_box": [], "letters": [], "last_activity": None, "awaiting_memory": False, "chat_id": None}
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    """Сохранить данные в файл JSON."""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_last_activity():
    """Обновить дату последней активности."""
    data = load_data()
    data['last_activity'] = datetime.now().strftime("%Y-%m-%d")
    save_data(data)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start: приветствие и планирование задач."""
    chat_id = update.effective_chat.id
    data = load_data()
    data["chat_id"] = chat_id
    save_data(data)
    await update.message.reply_text(
        "Привет! Я бот, который помогает замечать и записывать радостные события. " +
        "Напиши, что хорошего произошло с тобой сегодня, и я сохраню это!"
    )
    update_last_activity()

    # Планирование ежедневных и других задач
    job_queue = context.job_queue
    # Ежедневный отчет в 21:00
    job_queue.run_daily(daily_report, time(hour=21, minute=0, second=0), chat_id=chat_id)
    # Напоминание в 18:00
    job_queue.run_daily(reminder_to_write, time(hour=18, minute=0, second=0), chat_id=chat_id)
    # Недельный обзор воскресным вечером 22:15
    job_queue.run_daily(weekly_summary, time(hour=22, minute=15, second=0), chat_id=chat_id)
    # Праздничные и напоминание о бездействии ежедневно в 9:00
    job_queue.run_daily(holiday_and_inactive_check, time(hour=9, minute=0, second=0), chat_id=chat_id)
    # Отправка писем себе при наступлении срока (ежедневно в 00:00)
    job_queue.run_daily(send_due_letters, time(hour=0, minute=0, second=0), chat_id=chat_id)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка входящих текстовых сообщений: определение настроения или запись радости."""
    user_text = update.message.text.lower()
    data = load_data()
    chat_id = update.effective_chat.id

    update_last_activity()

    # Фильтрация нецензурных слов: не отвечаем и не записываем
    if any(bad in user_text for bad in BAD_WORDS):
        return

    # Добавление в коробочку воспоминаний, если был соответствующий запрос
    if data.get("awaiting_memory"):
        memory = update.message.text.strip()
        if memory:
            data["memory_box"].append({"date": datetime.now().strftime("%Y-%m-%d"), "text": memory})
            data["awaiting_memory"] = False
            save_data(data)
            await context.bot.send_message(chat_id=chat_id, text="Запись добавлена в коробочку воспоминаний! 😊")
        return

    # Обработка приветствия
    if any(greet in user_text for greet in GREETING_PATTERNS):
        response = random.choice(GREETING_RESPONSES)
        await context.bot.send_message(chat_id=chat_id, text=response)
        return

    # Сильная грусть
    if any(word in user_text for word in SEVERE_SAD_PATTERNS):
        await context.bot.send_message(chat_id=chat_id,
            text="Мне очень жаль это слышать. 😔 Я рядом, если захочешь поделиться.")
        return
    # Грусть
    if any(word in user_text for word in SAD_PATTERNS):
        await context.bot.send_message(chat_id=chat_id,
            text="Понимаю тебя. Тебе должно быть тяжело. Я рядом, если хочешь поговорить.")
        return
    # Тревога
    if any(word in user_text for word in ANXIETY_PATTERNS):
        await context.bot.send_message(chat_id=chat_id,
            text="Не волнуйся, все наладится. Я здесь, чтобы поддержать тебя.")
        return
    # Усталость
    if any(word in user_text for word in TIRED_PATTERNS):
        await context.bot.send_message(chat_id=chat_id,
            text="Отдых очень важен. Постарайся выспаться и восстановить силы. Ты молодец.")
        return
    # Нет радости
    if any(word in user_text for word in NO_JOY_PATTERNS):
        await context.bot.send_message(chat_id=chat_id,
            text="Понимаю, иногда так бывает. Дай себе время, хорошие моменты обязательно вернутся.")
        return

    # В остальных случаях считаем сообщение радостной записью
    today = datetime.now().strftime("%Y-%m-%d")
    if 'joys' not in data:
        data['joys'] = {}
    if today not in data['joys']:
        data['joys'][today] = []
    data['joys'][today].append(update.message.text)
    save_data(data)
    response = random.choice(JOY_ACCEPTANCE_RESPONSES)
    await context.bot.send_message(chat_id=chat_id, text=response)

async def random_joy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет случайную радость пользователя."""
    data = load_data()
    all_joys = []
    for joys in data.get("joys", {}).values():
        all_joys.extend(joys)
    if not all_joys:
        await update.message.reply_text("Пока нет записей о радостях.")
        return
    joy = random.choice(all_joys)
    await update.message.reply_text(f"Вот твоя случайная радость:\n\n{joy}")

async def memory_box(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает содержимое коробочки воспоминаний."""
    data = load_data()
    memories = data.get("memory_box", [])
    if not memories:
        await update.message.reply_text("Коробочка воспоминаний пуста.")
        return
    text = "Твои воспоминания:\n"
    for mem in memories:
        text += f"{mem['date']}: {mem['text']}\n"
    await update.message.reply_text(text)

async def start_letter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога для /letter."""
    keyboard = [["1 неделя", "2 недели", "1 месяц"], ["Отмена"]]
    reply_markup = {'keyboard': keyboard, 'one_time_keyboard': True, 'resize_keyboard': True}
    await update.message.reply_text("Через какое время напомнить тебе о письме? Выбери вариант:", reply_markup=reply_markup)
    return CHOOSE_PERIOD

async def choose_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор периода для отправки письма."""
    text = update.message.text
    if text == "Отмена":
        await update.message.reply_text("Команда отменена.")
        return ConversationHandler.END
    delay = None
    if text == "1 неделя":
        delay = 7 * 24 * 3600
    elif text == "2 недели":
        delay = 14 * 24 * 3600
    elif text == "1 месяц":
        delay = 30 * 24 * 3600
    else:
        await update.message.reply_text("Пожалуйста, выбери из предложенных вариантов или 'Отмена'.")
        return CHOOSE_PERIOD
    context.user_data['letter_delay'] = delay
    await update.message.reply_text("Напиши своё письмо, а я напомню тебе о нём через выбранный период.")
    return WRITE_LETTER

async def write_letter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запись письма и планирование напоминания."""
    content = update.message.text
    delay = context.user_data.get('letter_delay')
    if not delay:
        await update.message.reply_text("Произошла ошибка. Попробуй снова.")
        return ConversationHandler.END
    send_time = datetime.now() + timedelta(seconds=delay)
    data = load_data()
    data['letters'].append({"text": content, "send_time": send_time.strftime("%Y-%m-%d %H:%M:%S")})
    save_data(data)
    await update.message.reply_text("Письмо сохранено! Я напомню тебе о нём.")
    return ConversationHandler.END

async def cancel_letter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команда /letter отменена.")
    return ConversationHandler.END

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневный отчет с радостями в 21:00."""
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    chat_id = context.job.chat_id
    joys = data.get('joys', {}).get(today, [])
    if joys:
        text = f"Вот что тебя порадовало сегодня ({today}):\n"
        for joy in joys:
            text += f"- {joy}\\n"
        await context.bot.send_message(chat_id=chat_id, text=text)
        await context.bot.send_message(chat_id=chat_id,
            text="Если хочешь, добавь что-то в коробочку воспоминаний. Просто напиши это сообщение, и я сохраню.")
        data["awaiting_memory"] = True
    else:
        await context.bot.send_message(chat_id=chat_id,
            text="Сегодня ты ещё ничего не отметил как радость. Не забывай делиться хорошим!")
    save_data(data)

async def reminder_to_write(context: ContextTypes.DEFAULT_TYPE):
    """Напоминание написать радость в 18:00, если не писал."""
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    chat_id = context.job.chat_id
    if today not in data.get("joys", {}):
        await context.bot.send_message(chat_id=chat_id,
            text="Не забудь поделиться своей радостью за сегодня! 😊")

async def weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Недельный обзор по воскресеньям в 22:15."""
    if datetime.now().weekday() != 6:
        return
    data = load_data()
    chat_id = context.job.chat_id
    today = date.today()
    start = today - timedelta(days=today.weekday())
    all_joys = []
    for i in range(7):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        joys = data.get("joys", {}).get(day, [])
        all_joys.extend(joys)
    if not all_joys:
        await context.bot.send_message(chat_id=chat_id, text="На этой неделе не было записей о радостях.")
        return
    words = {}
    for joy in all_joys:
        for word in joy.split():
            word = word.strip('.,!?:;"').lower()
            if len(word) > 3:
                words[word] = words.get(word, 0) + 1
    top_words = sorted(words.items(), key=lambda x: x[1], reverse=True)[:3]
    topics = [f"«{w[0]}»" for w in top_words]
    summary = "Этой неделе чаще всего радовали: " + ", ".join(topics) + "."
    await context.bot.send_message(chat_id=chat_id, text=summary)

async def holiday_and_inactive_check(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет праздники и отсутствие активности."""
    data = load_data()
    chat_id = context.job.chat_id
    today = date.today()
    holidays = {
        (1, 1): "С Новым годом! 🎉 Пусть год будет наполнен радостью!",
        (12, 31): "С наступающим Новым годом! 🎊",
        (3, 8): "С 8 Марта! 🌷 Желаю тебе много радости!",
        (3, 1): "С Международным Днём весны и труда! 🌸",
        (6, 1): "С Днём защиты детей! Пусть радость будет с тобой всегда! 🎈",
    }
    msg = None
    if (today.month, today.day) in holidays:
        msg = holidays[(today.month, today.day)]
    last = data.get("last_activity")
    if last:
        last_date = datetime.strptime(last, "%Y-%m-%d").date()
        if (today - last_date).days >= 3:
            msg = "Давно не виделись! Как ты? 😊"
    if msg:
        await context.bot.send_message(chat_id=chat_id, text=msg)

async def send_due_letters(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет письма себе, если наступило время."""
    data = load_data()
    chat_id = context.job.chat_id
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    to_remove = []
    for letter in data.get("letters", []):
        if letter["send_time"] <= now:
            await context.bot.send_message(chat_id=chat_id,
                text=f"Письмо из прошлого пришло:\n\n{letter['text']}")
            to_remove.append(letter)
    for letter in to_remove:
        data["letters"].remove(letter)
    if to_remove:
        save_data(data)

def main():
    logging.basicConfig(level=logging.INFO)
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not TOKEN:
        print("Ошибка: TELEGRAM_TOKEN не задан!")
        return
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CommandHandler("random_joy", random_joy))
    app.add_handler(CommandHandler("memory_box", memory_box))
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("letter", start_letter)],
        states={
            CHOOSE_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_period)],
            WRITE_LETTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, write_letter)],
        },
        fallbacks=[CommandHandler("cancel", cancel_letter)],
    )
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
