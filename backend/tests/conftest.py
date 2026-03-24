"""Pytest configuration for backend contract tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Keep tests deterministic for providers that rely on generated fallback data.
os.environ.setdefault("PYTHONHASHSEED", "0")
