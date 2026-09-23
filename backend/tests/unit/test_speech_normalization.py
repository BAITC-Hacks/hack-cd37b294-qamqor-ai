import pytest

from app.voice.normalization import normalize_speech


@pytest.mark.parametrize("language,expected", [
    ("ru", "Стоимость: тридцать одна тысяча двести тенге. Скидка: пять процентов."),
    ("kk", "Стоимость: отыз бір мың екі жүз теңге. Скидка: бес пайыз."),
])
def test_money_and_percentage_preserve_values(language, expected):
    assert normalize_speech("Стоимость: **31 200 ₸**. Скидка: 5%.", language) == expected


@pytest.mark.parametrize("language,expected", [
    ("ru", "ноль запятая ноль пять тенге; двенадцать запятая пять ноль процента"),
    ("kk", "нөл үтір нөл бес теңге; он екі үтір бес нөл пайыз"),
])
def test_decimal_precision_and_leading_fraction_zeros(language, expected):
    assert normalize_speech("0,05 KZT; 12.50%", language) == expected


@pytest.mark.parametrize("language,expected", [
    ("ru", "Телефон: плюс семь семь ноль один ноль ноль ноль ноль ноль ноль один"),
    ("kk", "Телефон: плюс жеті жеті нөл бір нөл нөл нөл нөл нөл нөл бір"),
])
def test_phone_spells_every_digit_including_zeros(language, expected):
    assert normalize_speech("Телефон: +7 (701) 000-00-01", language) == expected


def test_local_phone_is_not_a_large_quantity():
    assert normalize_speech("8 701 000 00 01", "ru") == "восемь семь ноль один ноль ноль ноль ноль ноль ноль один"


@pytest.mark.parametrize("language,digits", [("ru", "ноль ноль один ноль два"), ("kk", "нөл нөл бір нөл екі")])
def test_policy_identifier_preserves_letters_separators_and_zeros(language, digits):
    value = normalize_speech("SQ-OGPO-00102", language)
    assert "эс кью" in value
    assert "оу джи пи оу" in value
    assert value.count("дефис") == 2
    assert value.endswith(digits)


@pytest.mark.parametrize("language,expected", [
    ("ru", "Срок до 1 октября 2026 года"),
    ("kk", "Срок до 2026 жылғы 1 қазан"),
])
def test_iso_date_preserves_calendar_day_month_year(language, expected):
    assert normalize_speech("Срок до 2026-10-01", language) == expected


def test_local_date_and_leap_day():
    assert normalize_speech("29.02.2024", "ru") == "29 февраля 2024 года"
    assert normalize_speech("29.02.2025", "ru") == "29.02.2025"
    assert normalize_speech("2026-13-01", "kk") == "2026-13-01"


@pytest.mark.parametrize("language,expected", [
    ("ru", "девять часов пять минут; двадцать один час одна минута"),
    ("kk", "сағат тоғыз нөл бес; сағат жиырма бір нөл бір"),
])
def test_time_preserves_hours_and_minutes(language, expected):
    assert normalize_speech("09:05; 21:01", language) == expected


def test_invalid_time_retained():
    assert normalize_speech("25:78", "ru") == "25:78"


def test_markdown_removed_customer_content_kept_internal_metadata_not_spoken():
    text = "# Ответ\n- **Полис** `SQ-OGPO-00102` готов.\n- [Проверить](https://example.test)\nsource_id: backend:123\nСценарий: SC26\n[SC26]"
    result = normalize_speech(text, "ru")
    assert "Полис" in result and "готов" in result and "Проверить" in result
    for marker in ("#", "*", "`", "SC26", "source_id", "backend", "https", "[", "]"):
        assert marker not in result


def test_does_not_drop_facts_inside_a_markdown_code_fence():
    assert normalize_speech("```text\nВозврат: 1500 ₸\n```", "ru") == "Возврат: одна тысяча пятьсот тенге."


def test_opaque_email_url_and_unknown_identifier_unchanged():
    text = "a_01@mail.example; https://example.test/policy_0001; ref_ab009"
    assert normalize_speech(text, "ru") == text


def test_long_identifier_and_leading_zero_not_read_as_quantities():
    assert normalize_speech("00042; 850314300121", "ru") == "ноль ноль ноль четыре два; восемь пять ноль три один четыре три ноль ноль один два один"


def test_abbreviations_are_language_selected_not_detected_from_input():
    assert normalize_speech("ЖСН", "ru") == "индивидуальный идентификационный номер"
    assert normalize_speech("ИИН", "kk") == "жеке сәйкестендіру нөмірі"


def test_negative_number_and_decimal_preserved():
    assert normalize_speech("−12,05 ₸", "kk") == "минус он екі үтір нөл бес теңге"


def test_grouped_currency_uses_entire_amount():
    assert normalize_speech("1\u202f234\u202f567 KZT", "ru") == "один миллион двести тридцать четыре тысячи пятьсот шестьдесят семь тенге"


def test_empty_answer_and_regular_kazakh_unchanged():
    assert normalize_speech("", "kk") == ""
    assert normalize_speech("Төлем туралы ақпаратты көріп тұрмын. Қазір полистің мәртебесін тексеремін.", "kk") == "Төлем туралы ақпаратты көріп тұрмын. Қазір полистің мәртебесін тексеремін."


@pytest.mark.parametrize("language,city,street,weekday,saturday", [
    ("ru", "Алматы", "проспект Абая", "с понедельника по пятницу", "суббота"),
    ("kk", "Алматы", "Абай даңғылы", "дүйсенбіден жұмаға дейін", "сенбі"),
])
def test_closed_office_source_mappings(language, city, street, weekday, saturday):
    result = normalize_speech("Almaty: Abai Ave 150. Mon-Fri 09:00-18:00, Sat 10:00-15:00.", language)
    for value in (city, street, weekday, saturday):
        assert value in result
    assert "сто пятьдесят" in result if language == "ru" else "жүз елу" in result
    for original in ("Almaty", "Abai Ave", "Mon-Fri", "Sat"):
        assert original not in result


def test_large_labeled_currency_is_quantity_but_unlabeled_number_is_identifier():
    assert normalize_speech("1234567 ₸", "kk") == "бір миллион екі жүз отыз төрт мың бес жүз алпыс жеті теңге"
    assert normalize_speech("1234567", "kk") == "бір екі үш төрт бес алты жеті"


def test_unknown_numeric_notation_never_partially_reinterpreted():
    assert normalize_speech("1,234.56 KZT; 1.234,56 ₸; 127.0.0.1; v1.2.3", "ru") == "1,234.56 KZT; 1.234,56 ₸; 127.0.0.1; v1.2.3"


def test_sentence_final_date_is_normalized_without_losing_period():
    assert normalize_speech("До 01.10.2026.", "ru") == "До 1 октября 2026 года."


def test_markdown_table_syntax_and_standalone_metadata_object_are_removed():
    text = '| Цена | Срок |\n| --- | --- |\n| 100 ₸ | 3 дня |\n{"scenario_id":"SC01","confidence":0.98}'
    result = normalize_speech(text, "ru")
    assert "сто тенге" in result and "три дня" in result
    assert all(value not in result for value in ("|", "---", "scenario", "SC01", "confidence", "0.98"))


@pytest.mark.parametrize("language,expected", [("ru", "с 09:00 до 18:00"), ("kk", "сағат тоғыздан он сегізге дейін")])
def test_clock_range_preserves_both_endpoints_and_gives_tts_grammatical_context(language, expected):
    assert normalize_speech("09:00-18:00", language) == expected


@pytest.mark.parametrize("text,expected", [
    ("10:00-15:00", "сағат оннан он беске дейін"),
    ("Сағат 20:00–23:00", "сағат жиырмадан жиырма үшке дейін"),
    ("00:00—01:00", "сағат нөлден бірге дейін"),
    ("сағат 09:00-ден 18:00-ге дейін", "сағат тоғыздан он сегізге дейін"),
    ("09:05-18:30", "сағат тоғыздан бес минут өткеннен сағат он сегізден отыз минут өткенге дейін"),
    ("09:00-18:05", "сағат тоғыздан сағат он сегізден бес минут өткенге дейін"),
    ("09:05-18:00", "сағат тоғыздан бес минут өткеннен сағат он сегізге дейін"),
])
def test_kazakh_clock_ranges_are_fully_spelled_without_losing_hours_or_minutes(text, expected):
    assert normalize_speech(text, "kk") == expected


def test_kazakh_existing_hour_label_is_not_duplicated():
    assert normalize_speech("Кездесу сағат 09:05.", "kk") == "Кездесу сағат тоғыз нөл бес."


def test_kazakh_actual_office_answer_has_no_numeric_time_left_for_tts():
    text = "Almaty: Abai Ave 150. Жұмыс уақыты: Mon-Fri 09:00-18:00, Sat 10:00-15:00."
    assert normalize_speech(text, "kk") == (
        "Алматы: Абай даңғылы жүз елу. Жұмыс уақыты: дүйсенбіден жұмаға дейін "
        "сағат тоғыздан он сегізге дейін, сенбі сағат оннан он беске дейін."
    )


def test_kazakh_invalid_time_range_is_preserved_without_guessing():
    assert normalize_speech("сағат 25:00-18:00", "kk") == "сағат 25:00-18:00"
