import numpy as np

from backend.src.prediction.liquidity_features import FEATURE_NAMES, BookObservation, LiquidityFeatureTracker
from backend.src.prediction.lobster_training import build_samples, grid_observations, select_probability_threshold


def _obs(spread=0.02, depth=1_000.0, mid=100.0, flow=0.0):
    step = spread / 2  # 10 evenly spaced levels per side, each 1/20 of the depth
    bids = tuple((mid - spread / 2 - i * step, depth / 20) for i in range(10))
    asks = tuple((mid + spread / 2 + i * step, depth / 20) for i in range(10))
    return BookObservation(mid=mid, spread=spread, bid_depth=depth / 2, ask_depth=depth / 2,
                           top_bid_size=depth / 20, top_ask_size=depth / 20, signed_volume_10s=flow,
                           bid_levels=bids, ask_levels=asks)


def test_features_are_scale_free():
    """A $580 book and a $100 book with 100x the size must look the same to the model."""
    small, large = LiquidityFeatureTracker(), LiquidityFeatureTracker()
    for step in range(80):
        wobble = 1 + 0.3 * np.sin(step)
        a, _ = small.update(_obs(spread=0.02 * wobble, depth=1_000 * wobble, mid=100.0, flow=50 * wobble))
        b, _ = large.update(_obs(spread=0.20 * wobble, depth=100_000 * wobble, mid=1_000.0, flow=5_000 * wobble))
    assert set(a) == set(FEATURE_NAMES)
    for name in FEATURE_NAMES:
        assert np.isclose(a[name], b[name]), name


def test_long_memory_sees_an_unusually_tight_baseline():
    """After 5 minutes at 4 bps, a minute at 2 bps is a tight baseline, not the new normal."""
    tracker = LiquidityFeatureTracker()
    for _ in range(300):
        tracker.update(_obs(spread=0.04))
    for _ in range(60):
        features, _ = tracker.update(_obs(spread=0.02))
    assert np.isclose(features["spread_ratio"], 1.0)        # the 60 s baseline has adapted
    assert features["spread_ratio_300s"] < 0.6              # the 5 min memory has not
    assert features["baseline_vs_300s"] < 0.6
    assert np.isclose(features["near_share"], 0.3)          # 3 of 10 equal levels per side


def test_labels_look_forward_and_features_never_see_the_future():
    calm = [_obs() for _ in range(200)]
    shocked = calm[:150] + [_obs(spread=0.08, depth=300.0)] * 20 + calm[:30]
    X_calm, y_calm = build_samples(calm, horizon=60, warmup=60)
    X_shock, y_shock = build_samples(shocked, horizon=60, warmup=60)

    assert y_calm.sum() == 0
    # Sample i sits at observation i + 60: second 100 sees the shock at 150 coming, second 60 does not.
    assert y_shock[100 - 60] == 1
    assert y_shock[60 - 60] == 0
    # Up to the shock, features are identical: nothing leaks backwards.
    assert np.array_equal(X_calm[: 150 - 60], X_shock[: 150 - 60])


def test_grid_takes_aggressor_side_from_executions():
    # Two book states; at t=1.5 a resting SELL (direction -1) of 300 is lifted by a buyer.
    book = np.array([[100.01e4, 500, 99.99e4, 400], [100.01e4, 200, 99.99e4, 400]], dtype=float)
    messages = np.array([[34_200.5, 1, 100, -1], [34_201.5, 4, 300, -1]], dtype=float)  # time, type, size, direction
    obs = grid_observations(book, messages)

    assert obs[0].signed_volume_10s == 0          # 09:30:01, before the trade
    assert obs[1].signed_volume_10s == 300        # 09:30:02, buyer-initiated
    assert np.isclose(obs[1].mid, 100.0) and np.isclose(obs[1].spread, 0.02)
    assert obs[1].ask_depth == 200 and obs[1].top_bid_size == 400


def test_threshold_selection_prefers_the_validation_f1_boundary():
    threshold = select_probability_threshold(np.asarray([0.05, 0.20, 0.65, 0.90]), np.asarray([0, 0, 1, 1]))
    assert 0.20 <= threshold <= 0.65
