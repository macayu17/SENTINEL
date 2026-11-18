import pickle

import numpy as np

from backend.src.prediction.liquidity_features import FEATURE_NAMES
from backend.src.prediction.liquidity_shock import LiquidityShockPredictor


class StubBooster:
    """Stands in for a native LightGBM booster: predict() returns P(shock)."""

    def __init__(self):
        self.last_shape = None

    def predict(self, features):
        self.last_shape = features.shape
        return np.asarray([0.8])


def _state():
    return {
        "mid_price": 100.0,
        "spread": 0.02,
        "total_depth": 5_000,
        "bid_depth": 2_600,
        "ask_depth": 2_400,
        "bid_levels": [{"price": 99.99, "size": 400}],
        "ask_levels": [{"price": 100.01, "size": 300}],
        "recent_signed_volume": 120,
        "volatility": 0.01,
    }


def test_predictor_feeds_the_shared_tracker_and_applies_calibration(tmp_path):
    path = tmp_path / "lobster.pkl"
    with path.open("wb") as output:
        pickle.dump({
            "model": StubBooster(),
            "artifact_type": "lobster_nasdaq_liquidity_shock",
            "feature_names": list(FEATURE_NAMES),
            "calibration": {"raw": [0.0, 1.0], "calibrated": [0.0, 0.5]},
        }, output)

    predictor = LiquidityShockPredictor(model_path=str(path))
    result = predictor.predict(_state())

    assert result["method"] == "lobster_nasdaq_model"
    assert result["probability"] == 0.4  # 0.8 raw through the calibration line
    assert predictor.model.last_shape == (1, len(FEATURE_NAMES))
    assert set(result["features"]) == set(FEATURE_NAMES)
