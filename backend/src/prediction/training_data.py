"""Generate labeled training data from market simulation."""

import pandas as pd
import numpy as np
from typing import List, Tuple, Dict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TrainingDataPoint:
    """Single training example with features and label."""
    
    # Features
    spread: float
    mid_price: float
    order_book_imbalance: float
    trade_flow: float
    volatility: float
    inventory: float
    
    # Label (target: future price movement direction)
    label: str  # "BUY", "SELL", "HOLD"
    
    # Metadata
    timestamp: float
    horizon_ticks: int = 10  # How many ticks ahead we look for label
    
    def to_dict(self) -> Dict:
        return {
            "spread": self.spread,
            "mid_price": self.mid_price,
            "order_book_imbalance": self.order_book_imbalance,
            "trade_flow": self.trade_flow,
            "volatility": self.volatility,
            "inventory": self.inventory,
            "label": self.label,
        }


class TrainingDataCollector:
    """Collects labeled training data from simulator state snapshots."""
    
    def __init__(self, price_movement_threshold: float = 0.001):
        """
        Args:
            price_movement_threshold: Minimum price movement (%) to classify as BUY/SELL.
                                      Below this = HOLD.
        """
        self.price_movement_threshold = price_movement_threshold
        self.data_points: List[TrainingDataPoint] = []
        self._price_window: List[Tuple[float, float]] = []  # (time, price)
    
    def add_market_state(
        self,
        timestamp: float,
        mid_price: float,
        spread: float,
        order_book_imbalance: float,
        trade_flow: float,
        volatility: float,
        inventory: float,
    ) -> None:
        """Add a market state snapshot to the price window."""
        self._price_window.append((timestamp, mid_price))
        # Keep only recent history for label generation
        if len(self._price_window) > 100:
            self._price_window.pop(0)
    
    def finalize_windows(self, horizon_ticks: int = 10) -> None:
        """
        Generate labels for all points in the price window by looking ahead.
        Call this after simulation completes to label the entire trajectory.
        """
        if len(self._price_window) < horizon_ticks:
            return
        
        for i in range(len(self._price_window) - horizon_ticks):
            current_time, current_price = self._price_window[i]
            future_time, future_price = self._price_window[i + horizon_ticks]
            
            # Calculate price movement
            price_movement_pct = (future_price - current_price) / current_price
            
            # Classify movement
            if price_movement_pct > self.price_movement_threshold:
                label = "BUY"  # Price will go up
            elif price_movement_pct < -self.price_movement_threshold:
                label = "SELL"  # Price will go down
            else:
                label = "HOLD"  # Price stable
            
            # Store the label with its index for matching to market state
            if hasattr(self, '_pending_labels'):
                self._pending_labels[i] = {
                    "label": label,
                    "future_price": future_price,
                    "movement_pct": price_movement_pct,
                }
    
    def create_training_dataframe(self) -> pd.DataFrame:
        """Convert collected data points to pandas DataFrame."""
        if not self.data_points:
            raise ValueError("No data points collected. Run simulation and add states first.")
        
        data_dicts = [point.to_dict() for point in self.data_points]
        df = pd.DataFrame(data_dicts)
        
        # Shuffle to break temporal correlation
        df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        
        return df
    
    def save_to_csv(self, filepath: Path) -> None:
        """Save training data to CSV for inspection."""
        df = self.create_training_dataframe()
        df.to_csv(filepath, index=False)
        print(f"Saved {len(df)} training points to {filepath}")
    
    @staticmethod
    def load_from_csv(filepath: Path) -> pd.DataFrame:
        """Load training data from CSV."""
        return pd.read_csv(filepath)


def generate_training_data_from_simulation(
    simulator,
    collector: TrainingDataCollector,
    sample_interval: int = 5,
) -> List[TrainingDataPoint]:
    """
    Extract training data from simulator state history.
    
    Args:
        simulator: MarketSimulator instance with _state_history populated.
        collector: TrainingDataCollector to accumulate data.
        sample_interval: Sample every Nth state to reduce data size.
    
    Returns:
        List of TrainingDataPoint objects.
    """
    training_data: List[TrainingDataPoint] = []
    
    if not hasattr(simulator, '_state_history') or not simulator._state_history:
        raise ValueError("Simulator must have state history. Run simulation first.")
    
    # Collect price trajectory for label generation
    for state in simulator._state_history:
        mid_price = state.get("mid_price", 100.0)
        timestamp = state.get("timestamp", 0.0)
        
        collector.add_market_state(
            timestamp=timestamp,
            mid_price=mid_price,
            spread=state.get("spread", 0.001),
            order_book_imbalance=state.get("order_book_imbalance", 0.0),
            trade_flow=state.get("trade_flow", 0.0),
            volatility=state.get("volatility", 0.02),
            inventory=state.get("inventory", 0.0),
        )
    
    # Generate labels by looking ahead in price trajectory
    collector.finalize_windows(horizon_ticks=10)
    
    # Now build training data points with sampling
    for i, state in enumerate(simulator._state_history[::sample_interval]):
        # Estimate label (simplified: use current vs next few states)
        # In production, you'd match this properly with finalized labels
        if i + 10 < len(simulator._state_history):
            current_price = state.get("mid_price", 100.0)
            future_states = simulator._state_history[i : min(i + 15, len(simulator._state_history))]
            future_price = max(s.get("mid_price", 100.0) for s in future_states)
            
            price_movement_pct = (future_price - current_price) / current_price
            
            if price_movement_pct > 0.002:
                label = "BUY"
            elif price_movement_pct < -0.002:
                label = "SELL"
            else:
                label = "HOLD"
        else:
            label = "HOLD"  # Insufficient lookahead
        
        point = TrainingDataPoint(
            spread=state.get("spread", 0.001),
            mid_price=state.get("mid_price", 100.0),
            order_book_imbalance=state.get("order_book_imbalance", 0.0),
            trade_flow=state.get("trade_flow", 0.0),
            volatility=state.get("volatility", 0.02),
            inventory=state.get("inventory", 0.0),
            label=label,
            timestamp=state.get("timestamp", 0.0),
        )
        
        training_data.append(point)
    
    collector.data_points = training_data
    return training_data
