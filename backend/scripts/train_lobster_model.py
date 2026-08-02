#!/usr/bin/env python3
"""Train a NASDAQ liquidity-shock model from LOBSTER snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle

import numpy as np

try:
    from _path_setup import BACKEND_ROOT, add_repo_root_to_path
except ModuleNotFoundError:
    from backend.scripts._path_setup import BACKEND_ROOT, add_repo_root_to_path

add_repo_root_to_path()

from backend.src.prediction.lobster_training import (
    FEATURE_NAMES,
    build_liquidity_samples,
    load_lobster_orderbook,
    select_probability_threshold,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a NASDAQ LOBSTER liquidity-shock model.")
    parser.add_argument("--orderbook", type=Path, required=True)
    parser.add_argument("--candidate-output", type=Path, default=BACKEND_ROOT / "models" / "candidates" / "lobster_nasdaq_liquidity_model.pkl")
    parser.add_argument("--report-output", type=Path, default=BACKEND_ROOT / "models" / "candidates" / "lobster_nasdaq_liquidity_report.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import average_precision_score, balanced_accuracy_score, f1_score, roc_auc_score

    orderbook = load_lobster_orderbook(args.orderbook)
    samples = build_liquidity_samples(orderbook)
    if len(samples) < 100 or len({sample["label"] for sample in samples}) < 2:
        raise RuntimeError("LOBSTER sample does not contain enough labelled examples from both classes.")
    train_end = max(1, int(len(samples) * 0.70))
    validation_end = max(train_end + 1, int(len(samples) * 0.85))
    train = samples[:train_end]
    validation = samples[train_end:validation_end]
    test = samples[validation_end:]
    x_train = np.asarray([[sample["features"][name] for name in FEATURE_NAMES] for sample in train], dtype=np.float32)
    y_train = np.asarray([sample["label"] for sample in train], dtype=np.int8)
    x_validation = np.asarray([[sample["features"][name] for name in FEATURE_NAMES] for sample in validation], dtype=np.float32)
    y_validation = np.asarray([sample["label"] for sample in validation], dtype=np.int8)
    x_test = np.asarray([[sample["features"][name] for name in FEATURE_NAMES] for sample in test], dtype=np.float32)
    y_test = np.asarray([sample["label"] for sample in test], dtype=np.int8)
    if len(np.unique(y_validation)) < 2 or len(np.unique(y_test)) < 2:
        raise RuntimeError("Chronological holdout contains one class; more LOBSTER history is required.")
    weights = np.where(y_train == 1, len(y_train) / max(1, 2 * y_train.sum()), len(y_train) / max(1, 2 * (len(y_train) - y_train.sum())))
    model = HistGradientBoostingClassifier(max_iter=150, max_leaf_nodes=15, l2_regularization=1.0, random_state=42)
    model.fit(x_train, y_train, sample_weight=weights)
    validation_probability = model.predict_proba(x_validation)[:, 1]
    threshold = select_probability_threshold(validation_probability, y_validation)
    probability = model.predict_proba(x_test)[:, 1]
    prediction = probability >= threshold
    metrics = {
        "roc_auc": float(roc_auc_score(y_test, probability)),
        "average_precision": float(average_precision_score(y_test, probability)),
        "balanced_accuracy": float(balanced_accuracy_score(y_test, prediction)),
        "f1": float(f1_score(y_test, prediction, zero_division=0)),
        "threshold": threshold,
        "test_positive_rate": float(y_test.mean()),
    }
    report = {
        "artifact_type": "lobster_nasdaq_liquidity_shock",
        "venue": "NASDAQ",
        "symbol": "AAPL",
        "source": "LOBSTER free sample mirror of the official sample",
        "snapshot_count": int(len(orderbook)),
        "labelled_samples": len(samples),
        "train_samples": len(train),
        "test_samples": len(test),
        "feature_names": FEATURE_NAMES,
        "label_definition": "future spread >= 2.5x past 100-event median OR future depth <= 40% of past median within 20 events",
        "metrics": metrics,
        "not_for_nse_runtime": True,
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
