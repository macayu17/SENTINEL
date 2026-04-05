#!/usr/bin/env python3
"""Run live-feed contract validation suites with provider-by-provider summary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_pytest(repo_root: Path, node_id: str) -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", "-q", node_id]
    result = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )

    output = (result.stdout or "") + (result.stderr or "")
    output = output.strip()
    return result.returncode == 0, output


def main() -> int:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]

    suites = [
        ("Provider: mock", "backend/tests/test_live_feed_contracts.py::test_mock_provider_contract"),
        ("Provider: binance", "backend/tests/test_live_feed_contracts.py::test_binance_provider_contract_without_network"),
        ("Provider: nse-style", "backend/tests/test_live_feed_contracts.py::test_nse_style_provider_contract_skeleton"),
        ("Provider: broker/exchange", "backend/tests/test_live_feed_contracts.py::test_broker_provider_contract_via_payload_normalization"),
        ("Dashboard payload contract", "backend/tests/test_dashboard_payload_contract.py"),
        ("Failover and reconnect", "backend/tests/test_live_feed_failover.py"),
        ("Normalization edge cases", "backend/tests/test_normalization_edges.py"),
    ]

    print("== SENTINEL Live-Feed Contract Validation ==")
    print(f"Repository root: {repo_root}")

    passed = 0
    failed = 0
    failures: list[tuple[str, str]] = []

    for label, node in suites:
        ok, output = _run_pytest(repo_root, node)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {label}")
        if ok:
            passed += 1
        else:
            failed += 1
            failures.append((label, output))

    print("\n== Summary ==")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total:  {len(suites)}")

    if failures:
        print("\n== Failure Details ==")
        for label, output in failures:
            print(f"-- {label} --")
            print(output or "No output captured")
            print()
        return 1

    print("\nAll live-feed contract checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
