import pickle

import numpy as np

from backend.src.prediction.liquidity_shock import LiquidityShockPredictor


class StubLobsterModel:
    def __init__(self):
        self.last_shape = None

    def predict_proba(self, features):
        self.last_shape = features.shape
        return np.asarray([[0.2, 0.8]])


def test_predictor_uses_lobster_artifact_features(tmp_path):
    model = StubLobsterModel()
    path = tmp_path / "lobster.pkl"
    with path.open("wb") as output:
        pickle.dump({"model": model, "artifact_type": "lobster_nasdaq_liquidity_shock"}, output)

    predictor = LiquidityShockPredictor(model_path=str(path))
    result = predictor.predict({
        "mid_price": 100.0,
        "spread": 0.02,
        "total_depth": 5_000,
        "bid_depth": 2_600,
        "ask_depth": 2_400,
        "volatility": 0.01,
    })

    assert result["method"] == "lobster_nasdaq_model"
    assert result["probability"] == 0.8
    assert predictor.model.last_shape == (1, 6)
