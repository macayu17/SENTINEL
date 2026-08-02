import numpy as np

from backend.src.prediction.lobster_training import build_liquidity_samples, select_probability_threshold


def test_liquidity_samples_use_past_baseline_and_future_shock_label():
    rows = []
    for index in range(12):
        spread = 0.02 if index < 8 else 0.08
        depth = 100.0 if index < 8 else 40.0
        rows.append([100.00 + spread, depth, 100.00, depth])
    samples = build_liquidity_samples(
        np.asarray(rows), baseline_events=4, horizon_events=2, sample_step=1,
        spread_multiplier=2.0, depth_ratio_threshold=0.5,
    )

    assert samples[0]["label"] == 0
    assert samples[3]["label"] == 1
    assert samples[3]["features"]["spread_ratio"] == 1.0
    assert samples[3]["features"]["depth_ratio"] == 1.0


def test_threshold_selection_prefers_the_validation_f1_boundary():
    threshold = select_probability_threshold(
        np.asarray([0.05, 0.20, 0.65, 0.90]), np.asarray([0, 0, 1, 1])
    )

    assert 0.20 <= threshold <= 0.65
