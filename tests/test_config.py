from pathlib import Path

from lot_export.config import AppConfig, load_config, save_config


def test_load_config_returns_defaults_when_missing(tmp_path: Path):
    assert load_config(tmp_path / "absent.json") == AppConfig()


def test_load_config_returns_defaults_when_invalid(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text("{ pas du json", encoding="utf-8")
    assert load_config(path) == AppConfig()


def test_save_then_load_roundtrip(tmp_path: Path):
    path = tmp_path / "sub" / "config.json"
    config = AppConfig().with_root_path(tmp_path / "audit").with_downloads_dir(tmp_path / "dl")

    save_config(config, path)

    loaded = load_config(path)
    assert loaded.root_path == tmp_path / "audit"
    assert loaded.downloads_path == tmp_path / "dl"


def test_with_methods_return_new_instances():
    config = AppConfig(root_path_be="a", downloads_dir="b")
    assert config.with_root_path("x") == AppConfig(root_path_be="x", downloads_dir="b")
    assert config.with_downloads_dir("y") == AppConfig(root_path_be="a", downloads_dir="y")
    assert config == AppConfig(root_path_be="a", downloads_dir="b")
