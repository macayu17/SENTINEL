"""Build leakage-safe liquidity-shock samples from recorded market depth."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import numpy as np


TRAINING_FEATURES = (
    "spread_ratio",
    "depth_ratio",
    "depth_imbalance_5",
    "absolute_imbalance_5",
    "mid_return_10s_bps",
    "realized_volatility_60s_bps",
    "volume_rate_60s",
)


def load_depth_records(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        with Path(path).open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {path}:{line_number}.") from exc
                if record.get("provider") != "upstox" or record.get("schema_version") != 1:
                    raise ValueError(f"Unsupported depth record in {path}:{line_number}.")
                records.append(record)
    return records


def _session_date(record: dict[str, Any]) -> str:
    timestamp = record.get("exchange_timestamp")
    if timestamp:
        return datetime.fromisoformat(str(timestamp)).date().isoformat()
    timestamp_ms = int(record["exchange_timestamp_ms"])
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date().isoformat()


def _total_depth(record: dict[str, Any]) -> float:
    return float(record["bid_depth_5"]) + float(record["ask_depth_5"])


def _past_features(
    rows: list[dict[str, Any]],
    timestamps: list[int],
    index: int,
    baseline_start: int,
) -> dict[str, float]:
    current = rows[index]
    past = rows[baseline_start:index]
    baseline_spread = median(float(row["spread_bps"]) for row in past)
    baseline_depth = median(_total_depth(row) for row in past)
    if baseline_spread <= 0 or baseline_depth <= 0:
        raise ValueError("Liquidity baseline must have positive spread and depth.")

    ten_seconds_ago = timestamps[index] - 10_000
    return_index = bisect_right(timestamps, ten_seconds_ago, baseline_start, index) - 1
    return_index = max(baseline_start, return_index)
    old_mid = float(rows[return_index]["mid_price"])
    current_mid = float(current["mid_price"])
    mid_return = math.log(current_mid / old_mid) * 10_000 if old_mid > 0 and current_mid > 0 else 0.0

    vol_start = bisect_left(timestamps, timestamps[index] - 60_000, baseline_start, index)
    mids = [float(row["mid_price"]) for row in rows[vol_start:index + 1]]
    returns = [math.log(mids[i] / mids[i - 1]) for i in range(1, len(mids)) if mids[i - 1] > 0 and mids[i] > 0]
    realized_volatility = float(np.std(returns)) * 10_000 if returns else 0.0

    volume_start = max(vol_start, baseline_start)
    elapsed = max(1.0, (timestamps[index] - timestamps[volume_start]) / 1000.0)
    volume_rate = max(0.0, float(current.get("volume", 0)) - float(rows[volume_start].get("volume", 0))) / elapsed
    imbalance = float(current["depth_imbalance_5"])

    return {
        "spread_ratio": float(current["spread_bps"]) / baseline_spread,
        "depth_ratio": _total_depth(current) / baseline_depth,
        "depth_imbalance_5": imbalance,
        "absolute_imbalance_5": abs(imbalance),
        "mid_return_10s_bps": mid_return,
        "realized_volatility_60s_bps": realized_volatility,
        "volume_rate_60s": volume_rate,
    }


def build_labeled_samples(
    records: Iterable[dict[str, Any]],
    *,
    baseline_seconds: int = 300,
    horizon_seconds: int = 60,
    min_baseline_observations: int = 60,
    sample_interval_seconds: int = 5,
    spread_multiplier: float = 2.5,
    depth_ratio_threshold: float = 0.4,
    required_future_hits: int = 2,
) -> list[dict[str, Any]]:
    """Create features from past data and labels from a separate future window."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(str(record["instrument_key"]), _session_date(record))].append(record)

    samples: list[dict[str, Any]] = []
    for (instrument_key, session_date), rows in sorted(groups.items()):
        rows.sort(key=lambda row: int(row["exchange_timestamp_ms"]))
        timestamps = [int(row["exchange_timestamp_ms"]) for row in rows]
        last_sample_timestamp: int | None = None

        for index, timestamp in enumerate(timestamps):
            if last_sample_timestamp is not None and timestamp - last_sample_timestamp < sample_interval_seconds * 1000:
                continue
            baseline_start = bisect_left(timestamps, timestamp - baseline_seconds * 1000, 0, index)
            if index - baseline_start < min_baseline_observations:
                continue
            if timestamp - timestamps[baseline_start] < baseline_seconds * 1000:
                continue
            future_end_time = timestamp + horizon_seconds * 1000
            if timestamps[-1] < future_end_time:
                continue
            future_end = bisect_right(timestamps, future_end_time, index + 1)
            future = rows[index + 1:future_end]
            if not future:
                continue

            features = _past_features(rows, timestamps, index, baseline_start)
            baseline_spread = float(rows[index]["spread_bps"]) / features["spread_ratio"]
            baseline_depth = _total_depth(rows[index]) / features["depth_ratio"]
            spread_hits = sum(
                float(row["spread_bps"]) >= baseline_spread * spread_multiplier
                for row in future
            )
            depth_hits = sum(
                _total_depth(row) <= baseline_depth * depth_ratio_threshold
                for row in future
            )

            samples.append({
                "instrument_key": instrument_key,
                "session_date": session_date,
                "timestamp_ms": timestamp,
                "features": features,
                "label": int(
                    spread_hits >= required_future_hits
                    or depth_hits >= required_future_hits
                ),
            })
            last_sample_timestamp = timestamp
    return samples


def chronological_split(
    samples: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = list(samples)
    dates = sorted({str(sample["session_date"]) for sample in rows})
    if len(dates) < 3:
        raise ValueError("At least three market sessions are required for chronological splits.")

    train_count = max(1, min(len(dates) - 2, round(len(dates) * 0.70)))
    validation_count = max(1, min(len(dates) - train_count - 1, round(len(dates) * 0.15)))
    train_dates = set(dates[:train_count])
    validation_dates = set(dates[train_count:train_count + validation_count])
    test_dates = set(dates[train_count + validation_count:])
    return (
        [sample for sample in rows if sample["session_date"] in train_dates],
        [sample for sample in rows if sample["session_date"] in validation_dates],
        [sample for sample in rows if sample["session_date"] in test_dates],
    )


def _matrix(samples: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    features = np.asarray(
        [[sample["features"][name] for name in TRAINING_FEATURES] for sample in samples],
        dtype=np.float64,
    )
    labels = np.asarray([sample["label"] for sample in samples], dtype=np.int8)
    return features, labels


def train_candidate(
    samples: Iterable[dict[str, Any]],
    *,
    min_sessions: int = 10,
    min_class_samples: int = 20,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Train and calibrate a candidate only when evaluation is meaningful."""
    rows = list(samples)
    sessions = sorted({str(sample["session_date"]) for sample in rows})
    report: dict[str, Any] = {
        "sample_count": len(rows),
        "session_count": len(sessions),
        "session_start": sessions[0] if sessions else None,
        "session_end": sessions[-1] if sessions else None,
        "gate": {"passed": False, "reasons": []},
    }
    if len(sessions) < min_sessions:
        report["gate"]["reasons"].append(
            f"need at least {min_sessions} sessions; found {len(sessions)}"
        )
        return None, report

    train, validation, test = chronological_split(rows)
    split_rows = {"train": train, "validation": validation, "test": test}
    report["splits"] = {
        name: {
            "samples": len(split),
            "positives": sum(int(sample["label"]) for sample in split),
            "sessions": len({sample["session_date"] for sample in split}),
        }
        for name, split in split_rows.items()
    }
    for name, split in split_rows.items():
        positives = sum(int(sample["label"]) for sample in split)
        negatives = len(split) - positives
        if positives < min_class_samples or negatives < min_class_samples:
            report["gate"]["reasons"].append(
                f"{name} needs {min_class_samples} samples from each class; found {positives} positive and {negatives} negative"
            )
    if report["gate"]["reasons"]:
        return None, report

    try:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import (
            average_precision_score,
            brier_score_loss,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
        )
    except ImportError as exc:
        raise RuntimeError("Install backend/requirements.txt before training.") from exc

    x_train, y_train = _matrix(train)
    x_validation, y_validation = _matrix(validation)
    x_test, y_test = _matrix(test)
    base_model = RandomForestClassifier(
        n_estimators=300,
        max_depth=10,
        min_samples_leaf=10,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    ).fit(x_train, y_train)
    try:
        from sklearn.frozen import FrozenEstimator

        model = CalibratedClassifierCV(FrozenEstimator(base_model), method="sigmoid")
    except ImportError:  # scikit-learn 1.5
        model = CalibratedClassifierCV(base_model, method="sigmoid", cv="prefit")
    model.fit(x_validation, y_validation)

    validation_probability = model.predict_proba(x_validation)[:, 1]
    thresholds = np.linspace(0.05, 0.95, 91)
    threshold = float(max(
        thresholds,
        key=lambda value: f1_score(y_validation, validation_probability >= value),
    ))
    test_probability = model.predict_proba(x_test)[:, 1]
    test_prediction = test_probability >= threshold
    prevalence = float(np.mean(y_test))
    baseline_probability = float(np.mean(y_train))
    baseline_brier = brier_score_loss(y_test, np.full(len(y_test), baseline_probability))
    brier = brier_score_loss(y_test, test_probability)
    metrics = {
        "threshold": threshold,
        "roc_auc": float(roc_auc_score(y_test, test_probability)),
        "average_precision": float(average_precision_score(y_test, test_probability)),
        "brier_score": float(brier),
        "brier_skill": float(1.0 - brier / baseline_brier) if baseline_brier else 0.0,
        "precision": float(precision_score(y_test, test_prediction, zero_division=0)),
        "recall": float(recall_score(y_test, test_prediction, zero_division=0)),
        "f1": float(f1_score(y_test, test_prediction)),
        "prevalence": prevalence,
    }
    report["metrics"] = metrics
    required_average_precision = max(0.05, prevalence * 1.25)
    if metrics["roc_auc"] < 0.65:
        report["gate"]["reasons"].append("test ROC AUC is below 0.65")
    if metrics["average_precision"] < required_average_precision:
        report["gate"]["reasons"].append(
            "test average precision does not beat prevalence by 25%"
        )
    if metrics["brier_skill"] <= 0:
        report["gate"]["reasons"].append("calibrated probabilities do not beat the prevalence baseline")
    report["gate"]["passed"] = not report["gate"]["reasons"]
    if not report["gate"]["passed"]:
        return None, report

    return {
        "artifact_version": 1,
        "model": model,
        "feature_names": TRAINING_FEATURES,
        "horizon_seconds": 60,
        "metrics": metrics,
        "session_start": report["session_start"],
        "session_end": report["session_end"],
    }, report
