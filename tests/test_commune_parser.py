from lot_export.services.commune_parser import extract_commune_codes


def test_extracts_5_digit_codes():
    assert extract_commune_codes("75001 69002") == ["75001", "69002"]


def test_extracts_corsican_codes_and_uppercases():
    assert extract_commune_codes("2a004 2B123") == ["2A004", "2B123"]


def test_deduplicates_preserving_order():
    assert extract_commune_codes("75001 75001 69002") == ["75001", "69002"]


def test_ignores_invalid_tokens():
    assert extract_commune_codes("abc 123 75001") == ["75001"]


def test_empty_text_returns_empty_list():
    assert extract_commune_codes("") == []
