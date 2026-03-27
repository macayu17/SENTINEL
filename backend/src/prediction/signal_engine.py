"""Rule-based and ML-driven signal engine for investor-facing BUY/SELL/HOLD decisions."""

from dataclasses import dataclass
from typing import Dict, Optional
from pathlib import Path
from ..utils.logger import get_logger

logger = get_logger("signal_engine")

# Lazy import to avoid hard dependency
try:
    from .signal_model import SignalModel
    SIGNAL_MODEL_AVAILABLE = True
except ImportError:
    SIGNAL_MODEL_AVAILABLE = False


@dataclass
class SignalInput:
    mid_price: float
    spread: float
    order_book_imbalance: float
    recent_price_movement: float
    trade_flow: float
    inventory: float


class SignalEngine:
    """
    Hybrid signal engine: ML model with rule-based fallback.

    If a trained model is available and loaded, uses it for predictions.
    Falls back to rule-based logic if model is unavailable or raises an error.
    
    This design preserves the same output contract while allowing
    both inference methods without breaking existing code.
    """

    def __init__(self, model_path: Optional[Path] = None):
        """
        Initialize signal engine.
        
        Args:
            model_path: Path to trained model pickle file. If None, uses rule-based only.
        """
        self.model: Optional[SignalModel] = None
        self.model_available = False
        self.model_path = model_path
        
        if model_path:
            self._try_load_model(model_path)
    
    def _try_load_model(self, model_path: Path) -> None:
        """Attempt to load trained model; log warning if unavailable."""
        if not SIGNAL_MODEL_AVAILABLE:
            logger.warning("SignalModel not available (sklearn may not be installed)")
            return
        
        try:
            self.model = SignalModel.load(model_path)
            self.model_available = True
            logger.info(f"Loaded trained signal model from {model_path}")
        except FileNotFoundError:
            logger.warning(f"Model file not found: {model_path}. Using rule-based fallback.")
        except Exception as e:
            logger.warning(f"Failed to load model: {e}. Using rule-based fallback.")

    def predict(self, signal_input: SignalInput) -> Dict[str, object]:
        """
        Predict signal using trained model or rule-based fallback.
        
        Returns:
            Dict with keys: signal, confidence, explanation, components, model_type
        """
        # Try ML model if available
        if self.model_available and self.model is not None:
            try:
                return self._predict_with_model(signal_input)
            except Exception as e:
                logger.warning(f"Model inference failed: {e}. Falling back to rule-based.")
        
        # Fall back to rule-based
        return self._predict_rule_based(signal_input)
    
    def _predict_with_model(self, signal_input: SignalInput) -> Dict[str, object]:
        """Predict using trained ML model."""
        # Build feature dict for model
        features = {
            "spread": signal_input.spread,
            "mid_price": signal_input.mid_price,
            "order_book_imbalance": signal_input.order_book_imbalance,
            "trade_flow": signal_input.trade_flow,
            "volatility": signal_input.recent_price_movement,  # Use price movement as volatility proxy
            "inventory": signal_input.inventory,
        }
        
        # Get prediction
        signal = self.model.predict(features)
        probs = self.model.predict_proba(features)
        
        # Confidence is probability of predicted action
        confidence = probs[signal]
        
        explanation = (
            f"Model prediction: {signal} "
            f"(BUY={probs['BUY']:.3f}, SELL={probs['SELL']:.3f}, HOLD={probs['HOLD']:.3f}) "
            f"[Spread={signal_input.spread:.4f}, Imbalance={signal_input.order_book_imbalance:.3f}]"
        )
        
        return {
            "signal": signal,
            "confidence": round(confidence, 3),
            "explanation": explanation,
            "components": {
                "buy_probability": round(probs['BUY'], 4),
                "sell_probability": round(probs['SELL'], 4),
                "hold_probability": round(probs['HOLD'], 4),
            },
            "model_type": "trained",
        }
    
    def _predict_rule_based(self, signal_input: SignalInput) -> Dict[str, object]:
        """Predict using deterministic rule-based logic (fallback)."""
        # Positive score favors BUY, negative favors SELL.
        momentum_score = signal_input.recent_price_movement * 0.45
        imbalance_score = signal_input.order_book_imbalance * 0.35
        flow_score = signal_input.trade_flow * 0.20

        # Friction and risk penalties.
        spread_penalty = min(0.35, max(0.0, signal_input.spread * 6.0))
        inventory_penalty = min(0.30, abs(signal_input.inventory) / 5000.0)

        raw_score = momentum_score + imbalance_score + flow_score - spread_penalty - inventory_penalty

        if raw_score > 0.08:
            signal = "BUY"
        elif raw_score < -0.08:
            signal = "SELL"
        else:
            signal = "HOLD"

        confidence = min(1.0, max(0.0, 0.5 + abs(raw_score)))

        explanation = (
            f"[Rule-based] Momentum={signal_input.recent_price_movement:.4f}, "
            f"Imbalance={signal_input.order_book_imbalance:.3f}, "
            f"Flow={signal_input.trade_flow:.3f}, "
            f"SpreadPenalty={spread_penalty:.3f}, "
            f"InventoryPenalty={inventory_penalty:.3f}."
        )

        return {
            "signal": signal,
            "confidence": round(confidence, 3),
            "explanation": explanation,
            "components": {
                "momentum_score": round(momentum_score, 4),
                "imbalance_score": round(imbalance_score, 4),
                "flow_score": round(flow_score, 4),
                "spread_penalty": round(spread_penalty, 4),
                "inventory_penalty": round(inventory_penalty, 4),
                "raw_score": round(raw_score, 4),
            },
            "model_type": "rule_based",
        }
