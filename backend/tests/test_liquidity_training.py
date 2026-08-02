from datetime import datetime, timedelta, timezone

from backend.src.prediction.liquidity_training import (
    build_labeled_samples,
    chronological_split,
    train_candidate,
)


def _session(day: int, *, shock_at: int = 20) -> list[dict]:
    start = datetime(2026, 7, day, 9, 15, tzinfo=timezone.utc)
    rows = []
    for second in range(30):
        shocked = shock_at <= second < shock_at + 2
        timestamp = start + timedelta(seconds=second)
        rows.append({
            "schema_version": 1,
            "provider": "upstox",
            "received_at": timestamp.isoformat(),
            "exchange_timestamp": timestamp.isoformat(),
            "exchange_timestamp_ms": int(timestamp.timestamp() * 1000),
            "instrument_key": "NSE_EQ|TEST",
            "last_price": 100.0,
            "volume": 1_000 + second * 10,
            "mid_price": 100.0,
            "spread_bps": 8.0 if shocked else 1.0,
            "bid_depth_5": 100 if shocked else 1_000,
            "ask_depth_5": 100 if shocked else 1_000,
            "depth_imbalance_5": 0.1,
            "bids": [{"price": 99.99, "quantity": 1_000, "orders": 5}],
            "asks": [{"price": 100.01, "quantity": 1_000, "orders": 5}],
        })
    return rows


def test_labels_use_past_baseline_and_future_horizon_without_leakage():
    samples = build_labeled_samples(
        _session(1),
        baseline_seconds=5,
        horizon_seconds=3,
        min_baseline_observations=5,
        sample_interval_seconds=1,
        required_future_hits=2,
    )
    by_second = {
        datetime.fromtimestamp(sample["timestamp_ms"] / 1000, tz=timezone.utc).second: sample
        for sample in samples
    }

    assert by_second[10]["label"] == 0
    assert by_second[18]["label"] == 1
    assert by_second[18]["features"]["spread_ratio"] == 1.0
    assert by_second[18]["features"]["depth_ratio"] == 1.0


def test_chronological_split_never_mixes_session_dates():
    samples = build_labeled_samples(
        _session(1) + _session(2) + _session(3),
        baseline_seconds=5,
        horizon_seconds=3,
        min_baseline_observations=5,
        sample_interval_seconds=1,
        required_future_hits=2,
    )

    train, validation, test = chronological_split(samples)

    assert {sample["session_date"] for sample in train} == {"2026-07-01"}
    assert {sample["session_date"] for sample in validation} == {"2026-07-02"}
    assert {sample["session_date"] for sample in test} == {"2026-07-03"}


def test_training_gate_rejects_insufficient_real_sessions():
    samples = build_labeled_samples(
        _session(1) + _session(2) + _session(3),
        baseline_seconds=5,
        horizon_seconds=3,
        min_baseline_observations=5,
        sample_interval_seconds=1,
    )

    artifact, report = train_candidate(samples, min_sessions=10)

    assert artifact is None
    assert report["gate"]["passed"] is False
    assert report["gate"]["reasons"] == ["need at least 10 sessions; found 3"]
