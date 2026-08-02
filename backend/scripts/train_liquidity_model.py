#!/usr/bin/env python3
"""Build and evaluate a candidate liquidity model from recorded depth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle
import sys

try:
    from _path_setup import BACKEND_ROOT, add_repo_root_to_path
except ModuleNotFoundError:
    from backend.scripts._path_setup import BACKEND_ROOT, add_repo_root_to_path

add_repo_root_to_path()

from backend.src.prediction.liquidity_training import (
    build_labeled_samples,
    load_depth_records,
    train_candidate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an offline liquidity-model candidate.")
    parser.add_argument("--input", action="append", type=Path, help="JSONL file or directory; repeat as needed.")
    parser.add_argument("--min-sessions", type=int, default=10)
    parser.add_argument("--candidate-output", type=Path, default=BACKEND_ROOT / "models" / "candidates" / "liquidity_model.pkl")
    parser.add_argument("--report-output", type=Path, default=BACKEND_ROOT / "models" / "candidates" / "liquidity_report.json")
    return parser.parse_args()


def _input_files(inputs: list[Path] | None) -> list[Path]:
    roots = inputs or [BACKEND_ROOT / "data" / "liquidity_depth"]
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(path for path in sorted(root.glob("*.jsonl")) if "smoke" not in path.stem.lower())
        else:
            files.append(root)
    return list(dict.fromkeys(path.resolve() for path in files if path.exists()))


def main() -> int:
    args = parse_args()
    files = _input_files(args.input)
    if not files:
        print("[error] No depth JSONL files found.", file=sys.stderr)
        return 1

    records = load_depth_records(files)
    samples = build_labeled_samples(records)
    artifact, report = train_candidate(samples, min_sessions=args.min_sessions)
    report.update({
        "input_files": [str(path) for path in files],
        "record_count": len(records),
        "label_horizon_seconds": 60,
        "baseline_seconds": 300,
    })
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if artifact is None:
        print("[blocked] Candidate failed the training gate.")
        for reason in report["gate"]["reasons"]:
            print(f"  - {reason}")
        print(f"[report] {args.report_output}")
        return 2

    args.candidate_output.parent.mkdir(parents=True, exist_ok=True)
    with args.candidate_output.open("wb") as output:
        pickle.dump(artifact, output)
    print(f"[ok] Candidate: {args.candidate_output}")
    print(f"[report] {args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
