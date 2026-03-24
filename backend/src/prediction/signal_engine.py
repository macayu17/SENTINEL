"""Rule-based signal engine for investor-facing BUY/SELL/HOLD decisions."""

from dataclasses import dataclass
from typing import Dict


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
    Deterministic rule-based signal engine.

    The scoring model is intentionally simple and explainable so it can be
    replaced later by an ML model while preserving the same output contract.
    """

    def predict(self, signal_input: SignalInput) -> Dict[str, object]:
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
            f"Momentum={signal_input.recent_price_movement:.4f}, "
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
        }
