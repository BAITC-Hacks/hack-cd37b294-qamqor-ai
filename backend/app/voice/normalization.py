"""Deterministic rendering of a *final* customer answer for speech only.

This module does not rewrite an answer, infer facts, change stored text, or touch
routing. Unknown identifiers are retained; digit sequences in known identifiers
are spelled individually, including every leading zero. Calendar dates are
validated before changing their notation. No extra model request is involved.
"""

import json
import re
from datetime import date


_DIGITS = {
    "ru": "ноль один два три четыре пять шесть семь восемь девять".split(),
    "kk": "нөл бір екі үш төрт бес алты жеті сегіз тоғыз".split(),
}
_TENS = {
    "ru": ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"],
    "kk": ["", "он", "жиырма", "отыз", "қырық", "елу", "алпыс", "жетпіс", "сексен", "тоқсан"],
}
_TEENS = "десять одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать семнадцать восемнадцать девятнадцать".split()
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_MONTHS = {
    "ru": "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(),
    "kk": "қаңтар ақпан наурыз сәуір мамыр маусым шілде тамыз қыркүйек қазан қараша желтоқсан".split(),
}
_LATIN = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", (
    "эй", "би", "си", "ди", "и", "эф", "джи", "эйч", "ай", "джей", "кей", "эл", "эм", "эн", "оу", "пи", "кью", "ар", "эс", "ти", "ю", "ви", "дабл ю", "экс", "уай", "зед",
)))
_NUMBER = r"[−-]?(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,]\d+)?"
_CURRENCIES = {
    "₸": ("тенге", "теңге"), "тг": ("тенге", "теңге"), "kzt": ("тенге", "теңге"),
    "тенге": ("тенге", "теңге"), "теңге": ("тенге", "теңге"),
    "₽": ("рублей", "рубль"), "rub": ("рублей", "рубль"),
    "$": ("долларов", "доллар"), "usd": ("долларов", "доллар"),
    "€": ("евро", "еуро"), "eur": ("евро", "еуро"),
}
_METADATA_KEYS = (
    r"scenario(?:_id)?|active_scenario|system_intent|source_ids?|boundary_checks|"
    r"state_version|operation_id|trace_id|event_id|conversation_id|turn_id|"
    r"router_latency(?:_ms)?|confidence|Маршрут|Сценарий"
)


def _plural(value: int, forms: tuple[str, str, str]) -> str:
    if 11 <= value % 100 <= 14:
        return forms[2]
    return forms[0] if value % 10 == 1 else forms[1] if 2 <= value % 10 <= 4 else forms[2]


def _digits(value: str, language: str) -> str:
    return " ".join(_DIGITS[language][int(char)] for char in value if char.isascii() and char.isdigit())


def _integer(value: int, language: str, feminine: bool = False) -> str:
    if value == 0:
        return _DIGITS[language][0]
    if value < 0:
        return "минус " + _integer(-value, language, feminine)
    if value >= 10**12:
        return _digits(str(value), language)
    words = []
    for scale, ru, kk in (
        (10**9, ("миллиард", "миллиарда", "миллиардов"), "миллиард"),
        (10**6, ("миллион", "миллиона", "миллионов"), "миллион"),
        (1000, ("тысяча", "тысячи", "тысяч"), "мың"),
    ):
        count, value = divmod(value, scale)
        if count:
            words.extend((_integer(count, language, scale == 1000), _plural(count, ru) if language == "ru" else kk))
    hundreds, value = divmod(value, 100)
    if hundreds:
        words.append(_HUNDREDS[hundreds] if language == "ru" else ("" if hundreds == 1 else _DIGITS[language][hundreds] + " ") + "жүз")
    if language == "ru" and 10 <= value < 20:
        words.append(_TEENS[value - 10])
    else:
        tens, units = divmod(value, 10)
        if tens:
            words.append(_TENS[language][tens])
        if units:
            words.append(("одна" if units == 1 else "две") if language == "ru" and feminine and units in (1, 2) else _DIGITS[language][units])
    return " ".join(words)


def _number(value: str, language: str) -> str:
    value = re.sub(r"[ \u00a0\u202f]", "", value)
    negative = value.startswith(("-", "−"))
    value = value.lstrip("-−")
    integer, *fraction = re.split(r"[.,]", value)
    # A leading zero can be an identifier. Never drop it by integer conversion.
    spoken = _digits(integer, language) if len(integer) > 1 and integer.startswith("0") else _integer(int(integer), language)
    if fraction:
        spoken += (" запятая " if language == "ru" else " үтір ") + _digits(fraction[0], language)
    return ("минус " if negative else "") + spoken


def _identifier(value: str, language: str) -> str:
    return ", дефис, ".join(" ".join(
        _DIGITS[language][int(char)] if char.isdigit() else _LATIN.get(char.upper(), char)
        for char in segment
    ) for segment in value.split("-"))


def normalize_speech(text: str, language: str) -> str:
    """Return speech text in the final response language; never detect language.

    Decimal digits are deliberately spoken individually after the separator so
    precision and trailing zeroes remain audible. Unlabelled long numbers and
    leading-zero values are treated as identifiers. Dates retain Arabic day/year
    in explicit month notation, allowing TTS to select grammatical case from the
    unchanged surrounding sentence instead of guessing it here.
    """
    language = "kk" if language == "kk" else "ru"
    held: list[str] = []

    def hold(value: str) -> str:
        held.append(value)
        return "\ue000" + chr(0xE100 + len(held) - 1) + "\ue001"

    def protect(pattern: str, transform, flags: int = 0) -> None:
        nonlocal text
        text = re.sub(pattern, lambda match: hold(transform(match)), text, flags=flags)

    def internal_object(match: re.Match) -> str:
        try:
            obj = json.loads(match[0])
        except ValueError:
            return match[0]
        return "" if obj and all(re.fullmatch(_METADATA_KEYS, key, re.I) for key in obj) else match[0]

    # Remove known *internal* traces, never a policy number or customer field.
    text = re.sub(r"\{[^{}\n]*\}", internal_object, text)
    text = re.sub(rf"(?im)^\s*[>*#-]*\s*[\"']?(?:{_METADATA_KEYS})[\"']?\s*[:=].*$", "", text)
    text = re.sub(r"\b(?:SC\d{2}|SYS_(?:UNCLEAR|OUT_OF_SCOPE|GOODBYE))\b", "", text)
    text = re.sub(r"\b(?:knowledge_base|mock_backend)\.json(?:#[^\s\]\)]+)?", "", text)
    text = re.sub(r"[\[(]\s*[\])]", "", text)
    text = re.sub(r"!?(\[([^\]]+)\])\([^\n)]*\)", lambda match: match[2], text)
    # Email and URLs are opaque factual values: do not strip their underscores,
    # parse their numbers as prices, or change path/identifier case.
    protect(r"https?://[^\s<>]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", lambda match: match[0])
    text = re.sub(r"(?m)^\s*```[^\n]*$", "", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)", "", text)
    text = re.sub(r"([*_~`])\1*", "", text)
    text = re.sub(r"(?m)^\s*\|?(?:\s*:?-{3,}:?\s*\|?)+\s*$", "", text)
    text = text.replace("|", ", ")

    def calendar(match: re.Match) -> str:
        raw = match[0]
        fields = re.split(r"[.-]", raw)
        year, month, day = map(int, fields if len(fields[0]) == 4 else fields[::-1])
        try:
            date(year, month, day)
        except ValueError:
            return raw  # An invalid/unknown date-like identifier stays exact.
        return f"{day} {_MONTHS[language][month - 1]} {year} года" if language == "ru" else f"{year} жылғы {day} {_MONTHS[language][month - 1]}"

    protect(r"(?<![\w.])(?:\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})(?!\w|\.\d)", calendar)
    # Ambiguous grouping / IP / version notation is not a decimal amount.
    # Preserve the complete token rather than changing only a matching suffix.
    protect(r"(?<!\w)\d+(?:[.,]\d+){2,}(?!\w)", lambda match: match[0])

    def clock(match: re.Match) -> str:
        hour, minute = map(int, match[0].split(":"))
        if hour > 23 or minute > 59:
            return match[0]
        if language == "kk":
            return "сағат " + _integer(hour, language) + (" нөл " + _integer(minute, language) if 0 < minute < 10 else " " + _integer(minute, language) if minute else "")
        return " ".join((_integer(hour, language), _plural(hour, ("час", "часа", "часов")), _integer(minute, language, True), _plural(minute, ("минута", "минуты", "минут")))) if minute else _integer(hour, language) + " " + _plural(hour, ("час", "часа", "часов")) + " ровно"

    def clock_range(match: re.Match) -> str:
        first, last = match[1], match[2]
        if any(int(hour) > 23 or int(minute) > 59 for hour, minute in (value.split(":") for value in (first, last))):
            return match[0]
        # As with calendar dates, let TTS inflect times in this explicit range
        # construction. Digit words in nominative case after RU "с/до" would
        # sound wrong. The exact clock values remain unchanged.
        return f"с {first} до {last}" if language == "ru" else f"{first} мен {last} аралығы"

    protect(r"(?<![\w:])(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})(?![\w:])", clock_range)
    protect(r"(?<![\w:])\d{1,2}:\d{2}(?![\w:])", clock)
    # International numbers, and the standard eleven-digit local KZ form.
    protect(r"(?<!\w)\+\d(?:[ ()-]*\d){6,14}(?!\d)", lambda match: "плюс " + _digits(match[0], language))
    protect(r"(?<![\w+])8[ ()-]*7\d{2}[ ()-]*\d{3}[ ()-]*\d{2}[ ()-]*\d{2}(?!\w)", lambda match: _digits(match[0], language))
    protect(r"(?<!\w)(?=[A-Za-z0-9-]*[A-Za-z])(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+(?!\w)|(?<!\w)(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{3,}(?!\w)", lambda match: _identifier(match[0], language))
    def currency(match: re.Match) -> str:
        value, unit = match[1], match[2].lower()
        label = _CURRENCIES[unit][int(language == "kk")]
        if language == "ru" and not re.search(r"[.,]", value):
            amount = int(re.sub(r"[ \u00a0\u202f]", "", value).replace("−", "-"))
            if unit in ("₽", "rub"):
                label = _plural(abs(amount), ("рубль", "рубля", "рублей"))
            elif unit in ("$", "usd"):
                label = _plural(abs(amount), ("доллар", "доллара", "долларов"))
        return _number(value, language) + " " + label

    currency_names = "|".join(re.escape(value) for value in _CURRENCIES)
    protect(rf"(?<!\w)({_NUMBER})\s*({currency_names})(?!\w)", currency, re.I)
    protect(rf"(?<!\w)({_NUMBER})\s*%", lambda match: _number(match[1], language) + (" пайыз" if language == "kk" else " процента" if re.search(r"[.,]", match[1]) else " " + _plural(abs(int(re.sub(r"[ \u00a0\u202f]", "", match[1]).replace("−", "-"))), ("процент", "процента", "процентов"))))
    protect(r"(?<![\w.,])(?:0\d+|\d{7,})(?![\w.,])", lambda match: _digits(match[0], language))
    # Decimal/general quantities; no matching inside an unknown identifier.
    protect(rf"(?<![\w./-]){_NUMBER}(?![\w/-]|\.\d)", lambda match: _number(match[0], language))

    abbreviations = {
        "ИИН": ("индивидуальный идентификационный номер", "жеке сәйкестендіру нөмірі"),
        "ЖСН": ("индивидуальный идентификационный номер", "жеке сәйкестендіру нөмірі"),
        "ДМС": ("дэ эм эс", "дэ эм эс"), "ОГПО": ("о гэ пэ о", "о гэ пэ о"),
        "SMS": ("эс эм эс", "эс эм эс"), "СМС": ("эс эм эс", "эс эм эс"),
    }
    text = re.sub(r"\b(?:" + "|".join(abbreviations) + r")\b", lambda match: abbreviations[match[0]][int(language == "kk")], text)
    # Closed mappings for English fragments in the actual starter-kit office
    # record. No guessing/transliteration of arbitrary customer names/addresses.
    for original, ru, kk in (
        ("Almaty", "Алматы", "Алматы"),
        ("Abai Ave", "проспект Абая", "Абай даңғылы"),
        ("Mon-Fri", "с понедельника по пятницу", "дүйсенбіден жұмаға дейін"),
        ("Sat", "суббота", "сенбі"),
    ):
        text = re.sub(r"\b" + re.escape(original) + r"\b", ru if language == "ru" else kk, text)
    text = re.sub(r"(?<!\w)Пн\s*[–—-]\s*Пт\b", "с понедельника по пятницу" if language == "ru" else "дүйсенбіден жұмаға дейін", text, flags=re.I)
    for short, ru, kk in (("ул", "улица", "көше"), ("пр", "проспект", "даңғыл"), ("тел", "телефон", "телефон")):
        text = re.sub(rf"(?<!\w){short}\.(?=\s)", ru if language == "ru" else kk, text, flags=re.I)
    text = re.sub(r"\s+[—–]\s+", ", ", text)
    text = re.sub(r"[ \t]*\n+[ \t]*", ". ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*([,.;!?])", r"\1", text)
    text = re.sub(r"([.!?])\s*\.", r"\1", text)
    text = re.sub(r"\.{2,}", ".", text).strip()
    text = re.sub(r"^(?:\.\s*)+", "", text)
    for index, value in enumerate(held):
        text = text.replace("\ue000" + chr(0xE100 + index) + "\ue001", value)
    return text.strip()
