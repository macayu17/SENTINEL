"""Generate a deterministic JSON validation snapshot for SENTINEL claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "output" / "validation_metrics.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.src.validation.metrics import classification_metrics, lead_time_summary


def build_validation_snapshot() -> dict:
    liquidity_warnings = [
        {"timestamp": 60, "triggered": True},
        {"timestamp": 120, "triggered": True},
        {"timestamp": 245, "triggered": True},
        {"timestamp": 390, "triggered": True},
    ]
    liquidity_events = [
        {"timestamp": 150},
        {"timestamp": 320},
        {"timestamp": 450},
    ]
    large_order_scores = [0.91, 0.83, 0.72, 0.21, 0.14, 0.68, 0.37, 0.88]
    large_order_labels = [True, True, True, False, False, False, False, True]

    return {
        "liquidity_warning": lead_time_summary(
            liquidity_warnings,
            liquidity_events,
            horizon_seconds=120,
        ),
        "large_order_detection": classification_metrics(
            large_order_scores,
            large_order_labels,
            threshold=0.7,
        ),
        "note": (
            "Synthetic deterministic check. Use real labeled scenarios before quoting "
            "production accuracy or lead-time numbers."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    snapshot = build_validation_snapshot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
