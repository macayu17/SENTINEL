"""Small deterministic metrics used to validate SENTINEL warning claims."""

from __future__ import annotations

from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence


def lead_time_summary(
    warnings: Iterable[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]],
    horizon_seconds: float,
) -> dict[str, Any]:
    """Match triggered warnings to future events and summarize lead time."""
    horizon = max(0.0, float(horizon_seconds))
    warning_times = sorted(
        _timestamp(item)
        for item in warnings
        if _is_triggered(item)
    )
    event_times = sorted(_timestamp(item) for item in events)

    lead_times: list[float] = []
    for event_time in event_times:
        candidates = [
            warning_time
            for warning_time in warning_times
            if 0 <= event_time - warning_time <= horizon
        ]
        if candidates:
            lead_times.append(round(event_time - candidates[0], 6))

    return {
        "total_events": len(event_times),
        "matched_events": len(lead_times),
        "coverage": _safe_ratio(len(lead_times), len(event_times)),
        "lead_times_seconds": lead_times,
        "mean_lead_time_seconds": round(mean(lead_times), 6) if lead_times else 0.0,
        "median_lead_time_seconds": round(median(lead_times), 6) if lead_times else 0.0,
        "min_lead_time_seconds": min(lead_times) if lead_times else 0.0,
        "max_lead_time_seconds": max(lead_times) if lead_times else 0.0,
    }


def classification_metrics(
    scores: Sequence[float],
    labels: Sequence[bool],
    threshold: float,
) -> dict[str, Any]:
    """Return thresholded binary classification metrics."""
    if len(scores) != len(labels):
        raise ValueError("scores and labels must have the same length.")

    cutoff = float(threshold)
    true_positive = false_positive = false_negative = true_negative = 0
    for score, label in zip(scores, labels):
        predicted = float(score) >= cutoff
        actual = bool(label)
        if predicted and actual:
            true_positive += 1
        elif predicted and not actual:
            false_positive += 1
        elif not predicted and actual:
            false_negative += 1
        else:
            true_negative += 1

    total = len(scores)
    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    return {
        "threshold": cutoff,
        "samples": total,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": precision,
        "recall": recall,
        "accuracy": _safe_ratio(true_positive + true_negative, total),
        "f1": _safe_ratio(2 * precision * recall, precision + recall),
    }


def _timestamp(item: Mapping[str, Any]) -> float:
    try:
        return float(item["timestamp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("metric rows must include a numeric timestamp.") from exc


def _is_triggered(item: Mapping[str, Any]) -> bool:
    if "triggered" in item:
        return bool(item["triggered"])
    if "warning" in item:
        return bool(item["warning"])
    if "score" in item and "threshold" in item:
        return float(item["score"]) >= float(item["threshold"])
    return True


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)
