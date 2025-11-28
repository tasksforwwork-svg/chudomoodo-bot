def clean_profanity(text: str) -> str:
    """
    Маскирует мат по корням, указанным в BAD_WORDS.
    Работает по принципу: если корень BAD_WORDS содержится в слове – слово заменяется.
    """
    lowered = text.lower()
    words = text.split()

    cleaned = []
    for w in words:
        lw = w.lower()
        replaced = False

        for bad in BAD_WORDS:
            if bad in lw:   # ← главное исправление!
                cleaned.append("*" * len(w))
                replaced = True
                break

        if not replaced:
            cleaned.append(w)

    return " ".join(cleaned)
