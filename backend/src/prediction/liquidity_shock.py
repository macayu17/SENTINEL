"""Liquidity stress assessment with an optional trained forecast model."""

from collections import deque
from statistics import median
from typing import Any, Dict, Optional
import pickle
import os
import numpy as np
from .features import FeatureExtractor
from ..utils.logger import get_logger

logger = get_logger("liquidity_shock")

FEATURE_NAMES = [
    "spread_ratio",
    "depth_ratio",
    "volatility_ratio",
    "mm_inventory_stress",
    "active_mm_count",
    "time_to_close",
]
LOBSTER_FEATURE_NAMES = [
    "spread_bps",
    "depth_log",
    "imbalance",
    "spread_ratio",
    "depth_ratio",
    "depth_change_ratio",
]

WARNING_LEVELS = {
    "safe": 80,
    "caution": 60,
    "warning": 40,
}
BASELINE_WINDOW = 60
MIN_BASELINE_OBSERVATIONS = 10


def _health_to_warning(health_score: float) -> str:
    if health_score >= 80:
        return "safe"
    elif health_score >= 60:
        return "caution"
    elif health_score >= 40:
        return "warning"
    else:
        return "critical"


class LiquidityShockPredictor:
    """Forecast with a loaded model, otherwise report current liquidity stress."""

    def __init__(self, model_path: Optional[str] = None) -> None:
        self.feature_extractor = FeatureExtractor()
        self.model: Optional[Any] = None
        self.model_metadata: Dict[str, Any] = {}
        self._model_path = model_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "models", "candidates",
            "lobster_nasdaq_liquidity_model.pkl",
        )

        # Try to load existing model
        if os.path.exists(self._model_path):
            try:
                with open(self._model_path, "rb") as f:
                    loaded = pickle.load(f)
                if isinstance(loaded, dict) and "model" in loaded:
                    self.model = loaded["model"]
                    self.model_metadata = loaded
                else:
                    self.model = loaded
                logger.info("Loaded pre-trained liquidity model from %s", self._model_path)
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
        self.reset()

    def reset(self) -> None:
        """Forget the previous run's adaptive liquidity baseline."""
        self._baseline: deque[tuple[float, float, float]] = deque(
            maxlen=BASELINE_WINDOW
        )

    def predict(self, market_state: Dict) -> Dict:
        """
        Forecast with a trained model or diagnose current observed stress.

        Returns:
            Dict with probability, health_score, warning_level, features, timestamp
        """
        timestamp = market_state.get("current_time", 0.0)

        if self.model is not None:
            if self.model_metadata.get("artifact_type") == "lobster_nasdaq_liquidity_shock":
                features = self._lobster_features(market_state)
                X = np.array([[features[f] for f in LOBSTER_FEATURE_NAMES]], dtype=np.float32)
                method = "lobster_nasdaq_model"
                market = "NASDAQ"
            else:
                features = self.feature_extractor.extract_liquidity_features(market_state)
                X = np.array([[features[f] for f in FEATURE_NAMES]], dtype=np.float32)
                method = "trained_model"
                market = None
            proba = self.model.predict_proba(X)[0]
            stress_score = float(proba[1]) if len(proba) > 1 else 0.0
            result = {
                "probability": round(stress_score, 4),
                "method": method,
                "horizon_seconds": 60,
            }
            if market:
                result["market"] = market
        else:
            features, stress_score, method = self._adaptive_diagnostic(market_state)
            result = {"method": method, "horizon_seconds": 0}

        health_score = max(0.0, min(100.0, (1.0 - stress_score) * 100))
        warning_level = _health_to_warning(health_score)

        result.update({
            "stress_score": round(stress_score, 4),
            "health_score": round(health_score, 1),
            "warning_level": warning_level,
            "features": features,
            "timestamp": timestamp,
        })
        return result

    def _lobster_features(self, market_state: Dict) -> Dict[str, float]:
        mid = max(0.01, float(market_state.get("mid_price", 100.0) or 100.0))
        spread = max(0.0, float(market_state.get("spread", 0.0) or 0.0))
        depth = max(1.0, float(market_state.get("total_depth", 0.0) or 0.0))
        bid_depth = max(0.0, float(market_state.get("bid_depth", 0.0) or 0.0))
        ask_depth = max(0.0, float(market_state.get("ask_depth", 0.0) or 0.0))
        imbalance = float(market_state.get("order_book_imbalance", 0.0) or 0.0)
        current_spread_ratio = spread / mid
        current = (current_spread_ratio, depth, 0.0)
        samples = list(self._baseline) or [current]
        baseline_spread_bps = median(sample[0] for sample in samples) * 10_000
        baseline_depth = median(sample[1] for sample in samples)
        previous_depth = samples[-1][1]
        features = {
            "spread_bps": spread / mid * 10_000,
            "depth_log": float(np.log1p(depth)),
            "imbalance": imbalance if bid_depth or ask_depth else 0.0,
            "spread_ratio": (spread / mid * 10_000) / max(1e-9, baseline_spread_bps),
            "depth_ratio": depth / max(1e-9, baseline_depth),
            "depth_change_ratio": depth / max(1e-9, previous_depth),
        }
        if features["spread_ratio"] <= 2.5 and features["depth_ratio"] >= 0.4:
            self._baseline.append(current)
        return features

    def _adaptive_diagnostic(
        self, market_state: Dict
    ) -> tuple[Dict[str, float], float, str]:
        mid = max(0.01, float(market_state.get("mid_price", 100.0) or 100.0))
        current = (
            max(0.0, float(market_state.get("spread", 0.0) or 0.0) / mid),
            max(1.0, float(market_state.get("total_depth", 0.0) or 0.0)),
            max(0.000001, float(market_state.get("volatility", 0.0) or 0.0)),
        )
        samples = list(self._baseline) or [current]
        features = FeatureExtractor(
            baseline_spread=median(sample[0] for sample in samples),
            baseline_depth=median(sample[1] for sample in samples),
            baseline_volatility=median(sample[2] for sample in samples),
        ).extract_liquidity_features(market_state)

        clamp = lambda value: max(0.0, min(1.0, value))
        depth_depletion = clamp(1.0 - features["depth_ratio"])
        spread_expansion = clamp((features["spread_ratio"] - 1.0) / 2.0)
        volatility_expansion = clamp((features["volatility_ratio"] - 1.0) / 3.0)
        baseline_depth = median(sample[1] for sample in samples)
        order_flow_pressure = clamp(
            abs(float(market_state.get("recent_signed_volume", 0.0) or 0.0))
            / max(current[1], baseline_depth * 0.1)
        )
        inventory_stress = clamp(features["mm_inventory_stress"])
        features.update({
            "depth_depletion": round(depth_depletion, 6),
            "spread_expansion": round(spread_expansion, 6),
            "volatility_expansion": round(volatility_expansion, 6),
            "order_flow_pressure": round(order_flow_pressure, 6),
        })

        if len(self._baseline) < MIN_BASELINE_OBSERVATIONS:
            self._baseline.append(current)
            return features, 0.0, "calibrating"

        stress_score = (
            0.30 * depth_depletion
            + 0.25 * spread_expansion
            + 0.20 * order_flow_pressure
            + 0.15 * volatility_expansion
            + 0.10 * inventory_stress
        )
        if stress_score < 0.2:
            self._baseline.append(current)
        return features, stress_score, "adaptive_stress"
