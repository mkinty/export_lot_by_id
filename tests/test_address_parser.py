from lot_export.services.address_parser import extract_addresses


def test_parses_example_entry():
    assert extract_addresses("05094_495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT") == {
        "05094": ["495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT"],
    }


def test_one_entry_per_line_grouped_by_insee():
    text = (
        "05094_495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT\n"
        "74143_12 rue des Alpes 74000 Annecy\n"
        "05094_3 ROUTE DU COL 05700 NOSSAGE ET BENEVENT\n"
    )
    assert extract_addresses(text) == {
        "05094": ["495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT", "3 ROUTE DU COL 05700 NOSSAGE ET BENEVENT"],
        "74143": ["12 RUE DES ALPES 74000 ANNECY"],
    }


def test_list_separators_and_extra_spaces_are_trimmed():
    text = '["05094_495  CHEMIN DE PIGE BOUIN 05700 NOSSAGE", "2a004_1 cours Napoléon 20000 Ajaccio"]'
    assert extract_addresses(text) == {
        "05094": ["495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE"],
        "2A004": ["1 COURS NAPOLÉON 20000 AJACCIO"],
    }


def test_inner_commas_are_kept_and_duplicates_removed():
    text = "05094_495, chemin de Pige\n05094_495, CHEMIN DE PIGE"
    assert extract_addresses(text) == {"05094": ["495, CHEMIN DE PIGE"]}


def test_ignores_entries_without_address():
    assert extract_addresses("05094_ \n74143 rue sans code") == {}
