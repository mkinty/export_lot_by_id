import pytest

from lot_export.services.formula_relocation import BROKEN_REFERENCE, relocate_formula


def test_aligned_formula_follows_its_row():
    assert relocate_formula('=IF(J57=1,U57,"")', "BG57", "BG3") == ('=IF(J3=1,U3,"")', False)


@pytest.mark.parametrize("origin, formula", [
    ("BG11", '=IF(J2=1,U2,"")'),   # lit plus haut : déplacer le décalage sortirait de la feuille
    ("BG2", '=IF(J29=1,U29,"")'),  # lit plus bas : le décalage lirait la ligne d'un autre ID
])
def test_shifted_formula_is_realigned_on_its_new_row(origin, formula):
    assert relocate_formula(formula, origin, "BG2") == ('=IF(J2=1,U2,"")', True)


def test_row_keeping_its_position_is_still_realigned():
    assert relocate_formula("=J29*2", "BG5", "BG5") == ("=J5*2", True)


def test_absolute_rows_and_other_cell_text_are_untouched():
    assert relocate_formula('=J9&"J2"&$A$1', "BG9", "BG2") == ('=J2&"J2"&$A$1', False)


def test_formula_reading_several_rows_keeps_its_offsets():
    assert relocate_formula("=J9+J8", "BG9", "BG5") == ("=J5+J4", False)


def test_formula_reading_another_sheet_is_only_shifted():
    assert relocate_formula("=IPE!A9+J9", "BG9", "BG5") == ("=IPE!A5+J5", False)


def test_impossible_reference_gives_ref_error_instead_of_failing():
    assert relocate_formula("=J9+J1", "BG9", "BG5") == (BROKEN_REFERENCE, False)


def test_formula_without_reference_is_unchanged():
    assert relocate_formula("=1+1", "BG9", "BG2") == ("=1+1", False)
