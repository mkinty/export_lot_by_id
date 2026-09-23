from lot_export.services.error_id_parser import extract_error_ids


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
