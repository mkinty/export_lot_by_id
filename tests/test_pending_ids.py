from pathlib import Path

from lot_export.models import ExportItem, ExportStatus, ExportSummary, NotExported
from lot_export.services.pending_ids import (
    clear_pending,
    load_pending,
    update_pending,
    update_pending_from_summary,
)


def test_missing_or_corrupt_file_is_an_empty_list(tmp_path: Path):
    path = tmp_path / "pending.json"
    assert load_pending(path) == {}

    path.write_text("{pas du json", encoding="utf-8")
    assert load_pending(path) == {}

    path.write_text("[1, 2]", encoding="utf-8")
    assert load_pending(path) == {}


def test_list_survives_between_runs_and_creates_its_folder(tmp_path: Path):
    path = tmp_path / "absent" / "pending.json"

    update_pending(path, {"74143_1": "fichier verrouillé"}, [])

    assert load_pending(path)["74143_1"]["reason"] == "fichier verrouillé"
    assert "date" in load_pending(path)["74143_1"]


def test_successes_are_removed_failures_updated_and_others_kept(tmp_path: Path):
    path = tmp_path / "pending.json"
    update_pending(path, {"74143_1": "a", "74143_2": "b", "38068_5": "c"}, [])

    pending = update_pending(path, {"74143_2": "nouvelle raison"}, ["74143_1"])

    assert list(pending) == ["74143_2", "38068_5"]
    assert pending["74143_2"]["reason"] == "nouvelle raison"
    assert pending["38068_5"]["reason"] == "c"


def test_update_from_summary_splits_exported_and_not_exported(tmp_path: Path):
    path = tmp_path / "pending.json"
    update_pending(path, {"74143_1": "ancien échec"}, [])
    summary = ExportSummary(items=[
        ExportItem(commune="74143", status=ExportStatus.SUCCESS, exported=("74143_1",),
                   not_exported=(NotExported("74143_9", "absent de la feuille Audit"),)),
    ])

    pending = update_pending_from_summary(path, summary)

    assert list(pending) == ["74143_9"]
    assert pending["74143_9"]["reason"] == "absent de la feuille Audit"


def test_clear_empties_the_list(tmp_path: Path):
    path = tmp_path / "pending.json"
    update_pending(path, {"74143_1": "a"}, [])

    clear_pending(path)

    assert load_pending(path) == {}
