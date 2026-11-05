from pathlib import Path

from lot_export.models import ExportItem, ExportStatus, ExportSummary, NotExported, NotExportedCause
from lot_export.services.export_report import CAUSE_ADVICE, report_path, write_not_exported_report


def _summary() -> ExportSummary:
    return ExportSummary(items=[
        ExportItem(commune="74143", source=Path("audit_74143.xlsx"), status=ExportStatus.SUCCESS, rows=3,
                   exported=("74143_1",), not_exported=(NotExported("74143_9", "absent de la feuille Audit"),)),
        ExportItem(commune="00000", status=ExportStatus.NOT_FOUND,
                   not_exported=(NotExported("00000_1", "fichier audit introuvable", NotExportedCause.NO_FILE),
                                 NotExported("00000_2", "fichier audit introuvable", NotExportedCause.NO_FILE))),
    ])


def _write(tmp_path: Path, summary: ExportSummary, invalid=(), duplicates=None):
    return write_not_exported_report(summary, invalid, duplicates or {}, tmp_path, "13", "ID erreur", Path("C:/source"))


def test_report_gives_totals_causes_details_and_input_problems(tmp_path: Path):
    path = _write(tmp_path, _summary(), ["04096_24I"], {"74143_1": 3})

    assert path == tmp_path / "non_exportes_LOT13.txt"
    text = path.read_text(encoding="utf-8-sig")
    assert "Dossier source : " in text
    assert "Valeurs distinctes demandées            : 4" in text
    assert "Valeurs reconnues dans la saisie        : 6" in text
    assert "1 (3 ligne(s) Audit)" in text
    assert f"2 : {NotExportedCause.NO_FILE.value}" in text
    assert text.index(NotExportedCause.NO_FILE.value) < text.index(NotExportedCause.VALUE_ABSENT.value)
    assert "74143_9 : absent de la feuille Audit" in text
    assert "00000_1 : fichier audit introuvable" in text
    assert "04096_24I" in text
    assert "74143_1 : saisi 3 fois" in text


def test_every_cause_has_advice():
    assert set(CAUSE_ADVICE) == set(NotExportedCause)


def test_duplicates_alone_produce_a_report(tmp_path: Path):
    clean = ExportSummary(items=[ExportItem(commune="74143", status=ExportStatus.SUCCESS, exported=("74143_1",))])

    assert _write(tmp_path, clean, duplicates={"74143_1": 2}) is not None


def test_no_anomaly_writes_nothing_and_removes_stale_report(tmp_path: Path):
    stale = report_path(tmp_path, "13")
    stale.write_text("ancien", encoding="utf-8")
    clean = ExportSummary(items=[ExportItem(commune="74143", status=ExportStatus.SUCCESS, exported=("74143_1",))])

    assert _write(tmp_path, clean) is None
    assert not stale.exists()
