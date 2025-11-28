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
    print(f"DEBUG: Processing message from {chat_id}: '{stripped}'")

    # Глобальная отмена - имеет высший приоритет
    if stripped.startswith("/cancel"):
        print("DEBUG: Cancel command detected")
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
        print("DEBUG: Cancel response sent")
        return

    # Команды
    if stripped.startswith("/start"):
        print("DEBUG: Start command detected")
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
        print("DEBUG: Start response sent")
        return

    if stripped.startswith("/stats"):
        print("DEBUG: Stats command detected")
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
        print("DEBUG: Stats response sent")
        return

    if stripped.startswith("/letter"):
        print("DEBUG: Letter command detected")
        handle_letter_command(chat_id)
        return

    # Проверка на мат ДО любой другой обработки
    if contains_profanity(text):
        print("DEBUG: Profanity detected")
        send_message(
            chat_id,
            add_emoji_prefix("Похоже, сегодня был трудный день! Понимаю, но давай попробуем обойтись без резких слов")
        )
        print("DEBUG: Profanity response sent")
        return

    # Состояние диалога
    state, meta = get_dialog_state(chat_id)
    print(f"DEBUG: Dialog state: {state}")
    
    if state == "await_letter_period":
        print("DEBUG: Handling letter period")
        handle_letter_period(chat_id, text)
        return
    if state == "await_letter_text":
        print("DEBUG: Handling letter text")
        handle_letter_text(chat_id, text, meta or {})
        return

    # Приветствие — отвечаем, но НЕ записываем как радость
    # Только если у пользователя мало радостей (первое взаимодействие)
    joy_count = get_joy_count(chat_id)
    if joy_count <= 2 and is_greeting_message(stripped):
        print("DEBUG: Greeting detected (new user)")
        send_message(chat_id, get_greeting_response())
        print("DEBUG: Greeting response sent")
        return
    elif is_greeting_message(stripped):
        print("DEBUG: Greeting detected (existing user), but skipping to avoid confusion")
        # Для существующих пользователей просто сохраняем приветствие как радость
        # вместо ответа приветствием

    # Проверяем все эмоциональные состояния последовательно
    print("DEBUG: Checking emotional states...")
    
    if is_severe_sad_message(stripped):
        print("DEBUG: Severe sadness detected")
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
        print("DEBUG: Severe sadness response sent")
        return

    if is_anxiety_message(stripped):
        print("DEBUG: Anxiety detected")
        send_message(chat_id, get_anxiety_response())
        add_sad_event(chat_id)
        print("DEBUG: Anxiety response sent")
        return

    if is_tired_message(stripped):
        print("DEBUG: Tiredness detected")
        send_message(chat_id, get_tired_response())
        add_sad_event(chat_id)
        print("DEBUG: Tiredness response sent")
        return

    if is_sad_message(stripped):
        print("DEBUG: Sadness detected")
        send_message(chat_id, get_sad_response())
        add_sad_event(chat_id)
        print("DEBUG: Sadness response sent")
        return

    if is_no_joy_message(stripped):
        print("DEBUG: No joy detected")
        send_message(chat_id, get_no_joy_response())
        print("DEBUG: No joy response sent")
        return

    # Если дошли сюда - это обычная радость
    print("DEBUG: Processing as regular joy")
    cleaned = clean_text_pipeline(text)
    if not cleaned:
        print("DEBUG: Empty after cleaning")
        send_message(
            chat_id,
            "Мне не удалось ничего сохранить.\n"
            "Попробуй написать чуть конкретнее, что тебя сегодня порадовало."
        )
        return

    print("DEBUG: Adding joy to database")
    add_joy(chat_id, cleaned)
    send_message(chat_id, get_joy_response(chat_id))
    print("DEBUG: Joy response sent")
