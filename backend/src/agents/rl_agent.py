"""A passive dummy agent wrapper used for RL training."""

from typing import List, Dict
from .base_agent import BaseAgent
from ..market.order import Order

class RLAgent(BaseAgent):
    """
    Acts as a placeholder in the MarketSimulator. 
    Its actions are externally injected by the RL Environment's step() function,
    but we need it in the simulator so its inventory and PnL are properly tracked
    by the existing simulator matching engine logic.
    """

    def __init__(self, agent_id: str, initial_capital: float = 100000.0) -> None:
        super().__init__(agent_id, "RL_MM", initial_capital, latency_seconds=0.0)
        self.max_inventory = 5000

    def decide_action(self, market_state: Dict) -> List[Order]:
        # Actions are intentionally left blank. The Gym environment directly injects 
        # the model's orders into the OrderBook before calling simulator.step().
        return []
