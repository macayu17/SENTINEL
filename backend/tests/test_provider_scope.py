import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_tracked_sources_do_not_reference_removed_zerodha_provider():
    result = subprocess.run(
        [
            "git",
            "grep",
            "-n",
            "-i",
            "-e",
            "zerodha",
            "-e",
            "kite",
            "--",
            ".",
            ":!backend/tests/test_provider_scope.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stdout
    assert result.stdout == ""
