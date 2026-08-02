#!/usr/bin/env python3
"""Train an offline FI-2010 mid-price-direction benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle
import sys

import numpy as np

try:
    from _path_setup import BACKEND_ROOT, add_repo_root_to_path
except ModuleNotFoundError:
    from backend.scripts._path_setup import BACKEND_ROOT, add_repo_root_to_path

add_repo_root_to_path()

from backend.src.prediction.fi2010_benchmark import HORIZON_EVENTS, load_fi2010_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a separate FI-2010 benchmark model.")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--horizon-events", type=int, choices=HORIZON_EVENTS, default=10)
    parser.add_argument("--max-train-samples", type=int, default=200_000)
    parser.add_argument("--max-test-samples", type=int, default=50_000)
    parser.add_argument("--candidate-output", type=Path, default=BACKEND_ROOT / "models" / "candidates" / "fi2010_midprice_benchmark.pkl")
    parser.add_argument("--report-output", type=Path, default=BACKEND_ROOT / "models" / "candidates" / "fi2010_midprice_benchmark_report.json")
    return parser.parse_args()


def _sample(features, labels, limit: int):
    if limit <= 0 or len(features) <= limit:
        return features, labels
    indices = np.linspace(0, len(features) - 1, num=limit, dtype=int)
    return features[indices], labels[indices]


def main() -> int:
    args = parse_args()
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
    except ImportError as exc:
        raise RuntimeError("Install backend/requirements.txt before training.") from exc

    train_features, train_labels = load_fi2010_file(args.train, horizon_events=args.horizon_events)
    test_features, test_labels = load_fi2010_file(args.test, horizon_events=args.horizon_events)
    train_features, train_labels = _sample(train_features, train_labels, args.max_train_samples)
    test_features, test_labels = _sample(test_features, test_labels, args.max_test_samples)
    model = HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=31, l2_regularization=1.0, random_state=42)
    model.fit(train_features, train_labels)
    prediction = model.predict(test_features)
    metrics = {
        "accuracy": float(accuracy_score(test_labels, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(test_labels, prediction)),
        "macro_f1": float(f1_score(test_labels, prediction, average="macro")),
    }
    report = {
        "artifact_type": "fi2010_midprice_direction_benchmark",
        "market": "Nasdaq OMX Finland",
        "horizon_events": args.horizon_events,
        "train_samples": len(train_features),
        "test_samples": len(test_features),
        "feature_count": int(train_features.shape[1]),
        "metrics": metrics,
        "not_for_nse_runtime": True,
        "source": "FI-2010 public limit-order-book benchmark",
    }
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.candidate_output.parent.mkdir(parents=True, exist_ok=True)
    with args.candidate_output.open("wb") as output:
        pickle.dump({"model": model, **report}, output)
    print(json.dumps(report, indent=2))
    print(f"[ok] Candidate: {args.candidate_output}")
    print(f"[report] {args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
