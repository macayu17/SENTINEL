"""Path helpers for direct execution of backend utility scripts."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_ROOT.parent


def _prepend(path: Path) -> Path:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
    return path


def add_backend_to_path() -> Path:
    return _prepend(BACKEND_ROOT)


def add_repo_root_to_path() -> Path:
    return _prepend(REPO_ROOT)
