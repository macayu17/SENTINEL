"""Detect unusually concentrated visible liquidity in an order book."""

from statistics import median
from typing import Dict, Optional


class LargeOrderDetector:
    """Flag a visible level that is large relative to the surrounding book."""

    def __init__(self, min_order_size: int = 1_000, concentration_multiple: float = 3.0) -> None:
        self.min_order_size = min_order_size
        self.concentration_multiple = concentration_multiple

    def reset(self) -> None:
        """Retained for the simulator lifecycle contract; this detector is stateless."""

    def detect(self, market_state: Dict) -> Optional[Dict]:
        levels = []
        for key, side in (("bid_levels", "buy"), ("ask_levels", "sell")):
            for level in market_state.get(key, []):
                size = int(level.get("size", 0) or 0)
                if size > 0:
                    levels.append({"side": side, "price": level.get("price"), "size": size})

        if len(levels) < 2:
            return None

        baseline = float(median(level["size"] for level in levels))
        largest = max(levels, key=lambda level: level["size"])
        threshold = max(float(self.min_order_size), baseline * self.concentration_multiple)
        if largest["size"] < threshold:
            return None

        size_multiple = largest["size"] / max(1.0, baseline)
        total_depth = max(1, int(market_state.get("total_depth", 0) or sum(level["size"] for level in levels)))
        confidence = min(0.99, 0.5 + 0.05 * (size_multiple - self.concentration_multiple))
        return {
            "pattern": "large_level",
            "source": "visible_order_book",
            "side": largest["side"],
            "price": largest["price"],
            "estimated_size": largest["size"],
            "confidence": round(confidence, 4),
            "depth_share": round(largest["size"] / total_depth, 4),
            "size_multiple": round(size_multiple, 2),
        }
