import os

from backend.src.utils import config as config_module


def test_load_environment_files_reads_backend_env_from_project_root(monkeypatch, tmp_path):
    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    (backend_root / ".env").write_text("SENTINEL_TEST_VALUE=loaded-from-backend\n", encoding="utf-8")

    monkeypatch.delenv("SENTINEL_TEST_VALUE", raising=False)

    config_module._load_environment_files(backend_root=backend_root, project_root=tmp_path)

    assert os.getenv("SENTINEL_TEST_VALUE") == "loaded-from-backend"


def test_reload_environment_values_fills_empty_runtime_value(monkeypatch, tmp_path):
    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    (backend_root / ".env").write_text("SENTINEL_TEST_VALUE=loaded-value\n", encoding="utf-8")

    monkeypatch.setenv("SENTINEL_TEST_VALUE", "")

    config_module._reload_environment_values(
        ["SENTINEL_TEST_VALUE"],
        backend_root=backend_root,
        project_root=tmp_path,
    )

    assert os.getenv("SENTINEL_TEST_VALUE") == "loaded-value"
