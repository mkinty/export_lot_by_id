from lot_export.services.error_id_parser import (
    extract_error_ids,
    find_duplicate_error_ids,
    find_invalid_error_ids,
)


def test_groups_ids_by_insee_code():
    assert extract_error_ids("[ 74143_1,  74143_2,   74143_3]") == {
        "74143": ["74143_1", "74143_2", "74143_3"],
    }


def test_multiple_communes_preserve_order():
    assert extract_error_ids("38068_207\n74143_1\n38068_2") == {
        "38068": ["38068_207", "38068_2"],
        "74143": ["74143_1"],
    }


def test_corsican_codes_are_uppercased():
    assert extract_error_ids("2a004_12") == {"2A004": ["2A004_12"]}


def test_deduplicates_ids():
    assert extract_error_ids("74143_1 74143_1") == {"74143": ["74143_1"]}


def test_ignores_plain_commune_codes_and_invalid_tokens():
    assert extract_error_ids("74143 abc_1 1234_5 74143_") == {}


def test_find_invalid_lists_tokens_that_are_not_error_ids():
    text = "74143_1, 1234_5 ; 74143_1_bis\n74143 [2a004_12]"
    assert find_invalid_error_ids(text) == ["1234_5", "74143_1_bis", "74143"]


def test_find_invalid_is_empty_for_valid_input():
    assert find_invalid_error_ids("[ 74143_1,  2A004_12 ]\n38068_207") == []


def test_find_invalid_reports_a_typo_in_an_id():
    assert find_invalid_error_ids("04096_220\n04096_24I") == ["04096_24I"]


def test_find_duplicates_counts_repeated_ids():
    assert find_duplicate_error_ids("74143_1 74143_2\n74143_1 2a004_1 2A004_1 74143_1") == {
        "74143_1": 3, "2A004_1": 2}
