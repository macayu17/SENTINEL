import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.utils import config as config_module


def test_load_environment_files_reads_backend_env_from_project_root(monkeypatch, tmp_path):
    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    (backend_root / ".env").write_text("GROWW_API_KEY=loaded-from-backend\n", encoding="utf-8")

    monkeypatch.delenv("GROWW_API_KEY", raising=False)

    config_module._load_environment_files(backend_root=backend_root, project_root=tmp_path)

    assert os.getenv("GROWW_API_KEY") == "loaded-from-backend"
