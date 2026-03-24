<<<<<<< HEAD
"""Market simulator — orchestrates agents, order book, and state tracking using a Discrete Event Kernel."""

from typing import List, Dict, Optional, Any
=======
"""Market simulator — orchestrates agents, order book, and state tracking."""

from typing import List, Dict, Optional
>>>>>>> upstream/main
import math
from collections import deque
from .order_book import OrderBook
from .order import Order
from .trade import Trade
<<<<<<< HEAD
from .kernel import EventKernel, EventType
=======
>>>>>>> upstream/main
from ..agents.base_agent import BaseAgent
from ..utils.logger import get_logger

logger = get_logger("simulator")


class MarketSimulator:
    """
<<<<<<< HEAD
    Multi-agent market microstructure simulator powered by an Event Kernel.
=======
    Multi-agent market microstructure simulator.

    Each step:
    1. Sorts agents by latency (fastest first).
    2. Calls each agent's decide_action() with the current market state.
    3. Submits orders to the central OrderBook.
    4. Updates agent positions from resulting trades.
    5. Records history for downstream analysis.
>>>>>>> upstream/main
    """

    def __init__(
        self,
        agents: List[BaseAgent],
        initial_price: float = 100.0,
        duration_seconds: int = 23_400,
        mode: str = "SANDBOX",
    ) -> None:
<<<<<<< HEAD
        self.agents = agents
        self.order_book = OrderBook()
        self.kernel = EventKernel()
=======
        self.agents = sorted(agents, key=lambda a: a.latency_seconds)
        self.order_book = OrderBook()
>>>>>>> upstream/main
        self.initial_price = initial_price
        self.duration_seconds = duration_seconds

        # State
<<<<<<< HEAD
=======
        self.current_time: float = 0.0
>>>>>>> upstream/main
        self.current_price: float = initial_price
        self.step_count: int = 0
        self.running: bool = False
        self.mode: str = mode

        # History tracking
        self._price_history: deque = deque(maxlen=500)
        self._price_history.append(initial_price)
        self._state_history: List[Dict] = []
        self._all_trades: List[Trade] = []
<<<<<<< HEAD
        
        # New Microstructure Metrics
        self._recent_volume_history = deque(maxlen=100) # (time, signed_qty)
        self._recent_signed_volume: float = 0.0

    @property
    def current_time(self):
        return self.kernel.current_time

    def reset(self, seed: Optional[int] = None) -> None:
        """Reset the simulator for a new episode."""
        if seed is not None:
            import random
            random.seed(seed)
            import numpy as np
            np.random.seed(seed)
            
        self.order_book = OrderBook()
        self.kernel.clear()
        self.current_price = self.initial_price
        self.step_count = 0
        self.running = False
        
        self._price_history.clear()
        self._price_history.append(self.initial_price)
        self._state_history.clear()
        self._all_trades.clear()
        
        # Initial seed liquidity
        self._seed_order_book()
        
        for agent in self.agents:
            if hasattr(agent, 'reset'):
                agent.reset()
            else:
                agent.position = 0
                agent.cash = agent.initial_capital if hasattr(agent, 'initial_capital') else 10000.0
                agent.active_orders = {}

            # Ignore RL agents in standard automatic waking as Gym will drive them manually
            if getattr(agent, "agent_type", "") != "RL_MM":
                # Schedule first wakeup randomly within the first second to avoid sync-clustering
                import random
                first_wake = random.uniform(0.01, 1.0)
                self.kernel.schedule(first_wake, EventType.WAKEUP, self._agent_wakeup, agent)

        return self.get_market_state()
=======

        # Seed the order book with initial liquidity
        self._seed_order_book()
>>>>>>> upstream/main

    def _seed_order_book(self) -> None:
        """Place initial resting orders to bootstrap the book."""
        for i in range(10):
            offset = (i + 1) * 0.01
            bid = Order(
                agent_id="SEED",
                side="buy",
                order_type="limit",
                price=round(self.initial_price - offset, 2),
                quantity=500,
            )
            ask = Order(
                agent_id="SEED",
                side="sell",
                order_type="limit",
                price=round(self.initial_price + offset, 2),
                quantity=500,
            )
            from .order import OrderSide, OrderType
            bid.side = OrderSide.BUY
            bid.order_type = OrderType.LIMIT
            ask.side = OrderSide.SELL
            ask.order_type = OrderType.LIMIT
            self.order_book.add_order(bid)
            self.order_book.add_order(ask)

<<<<<<< HEAD
    def _process_order(self, order: Order) -> None:
        """Exchange receives and processes the order."""
        if self.mode == "SANDBOX":
            trades = self.order_book.add_order(order)
            self._all_trades.extend(trades)
            
            # Post-trade processing (position updates and metrics)
            for trade in trades:
                # Update last trade price
                self.current_price = trade.price
                self._price_history.append(self.current_price)
                signed_qty = trade.quantity if trade.buyer_agent_id != "SEED" else -trade.quantity
                self._recent_volume_history.append((self.kernel.current_time, signed_qty))
                
                # Signal agents they executed
                for agent in self.agents:
                    if agent.agent_id in (trade.buyer_agent_id, trade.seller_agent_id):
                        # Simulating execution report network delay latency back to agent
                        self.kernel.schedule(agent.latency_seconds, EventType.MARKET_DATA, agent.update_position, trade)
        else:
            pass # LIVE_SHADOW mode logic

    def _agent_wakeup(self, agent: BaseAgent) -> None:
        """Trigger an agent to observe the book and potentially issue orders."""
        if not self.running:
            return
            
        try:
            state = self.get_market_state()
            orders = agent.decide_action(state)
            
            # Schedule orders to arrive at the exchange after agent's structural latency
            for order in orders:
                self.kernel.schedule(agent.latency_seconds, EventType.ORDER_ARRIVAL, self._process_order, order)
                
        except Exception as e:
            logger.error(f"Agent {agent.agent_id} error: {e}")
            
        # Reschedule next WAKEUP. Defaulting to 1 second if agent doesn't specify an explicit interval.
        interval = getattr(agent, "wakeup_interval", 1.0)
        
        # Add slight jitter to prevent artificial clustering using kernel current time hash
        import random
        jitter = random.uniform(0.9, 1.1)
        
        self.kernel.schedule(interval * jitter, EventType.WAKEUP, self._agent_wakeup, agent)

    def run(self, steps: Optional[int] = None) -> Dict:
        """Run the simulation synchronously. (Steps is now treated as seconds for legacy support)."""
        self.reset()
        self.running = True
        target_time = steps if steps else self.duration_seconds
        
        logger.info(f"Starting kernel event loop until T={target_time}s")
        self.kernel.run_until(target_time)
        self.running = False
        
        # Synthesize state changes for standard output return
        self.step_count = int(self.kernel.current_time)
        return self.get_results()

    def step(self) -> Dict:
        """Legacy 1-second fixed step support, mainly used by older gym env wrappers."""
        if not self.running:
            self.running = True
        
        self.step_count += 1
        # Advance kernel by exactly 1 unit of time
        target = self.kernel.current_time + 1.0
        self.kernel.run_until(target)
        
        # Return state for RL or metrics
        state = self.get_market_state()
        self._state_history.append(state)
=======
    def run(self, steps: Optional[int] = None) -> Dict:
        """Run the simulation for a given number of steps (or until duration)."""
        self.running = True
        max_steps = steps or self.duration_seconds
        logger.info(f"Starting simulation: {len(self.agents)} agents, {max_steps} steps")

        for i in range(max_steps):
            if not self.running:
                break
            self.step()
            if (i + 1) % 1000 == 0:
                logger.info(
                    f"Step {i+1}/{max_steps} | Price={self.current_price:.2f} | "
                    f"Trades={len(self._all_trades)} | Spread={self.order_book.spread or 0:.4f}"
                )

        self.running = False
        return self.get_results()

    def step(self) -> Dict:
        """Process one simulation time step."""
        self.current_time += 1.0
        self.step_count += 1

        market_state = self.get_market_state()
        step_trades: List[Trade] = []

        # Each agent decides and submits orders
        for agent in self.agents:
            try:
                orders = agent.decide_action(market_state)
                for order in orders:
                    # In SANDBOX mode, the market is deterministic and driven by agents.
                    if self.mode == "SANDBOX":
                        trades = self.order_book.add_order(order)
                        step_trades.extend(trades)
                    else:
                        # In LIVE_SHADOW mode, agents paper-trade against the exogenous LIVE book.
                        # Real orders are dropped so they do not impact the live clone.
                        # Advanced paper-matching slippage logic would go here.
                        pass
            except Exception as e:
                logger.error(f"Agent {agent.agent_id} error: {e}")

        # Update agent positions from trades
        for trade in step_trades:
            for agent in self.agents:
                if agent.agent_id in (trade.buyer_agent_id, trade.seller_agent_id):
                    agent.update_position(trade)

        # Update price from last trade
        if step_trades:
            self.current_price = step_trades[-1].price
        elif self.order_book.mid_price:
            self.current_price = self.order_book.mid_price

        self._price_history.append(self.current_price)
        self._all_trades.extend(step_trades)

        # Record state
        state = self.get_market_state()
        state["step_trades"] = len(step_trades)
        self._state_history.append(state)

>>>>>>> upstream/main
        return state

    def get_market_state(self) -> Dict:
        """Return the current market state snapshot."""
        depth_data = self.order_book.get_depth(levels=10)
        total_depth = self.order_book.get_total_depth(levels=10)
        volatility = self._compute_volatility()
<<<<<<< HEAD
        recent_price_change = 0.0
        prices = list(self._price_history)
        if len(prices) >= 5 and prices[-5] > 0:
            recent_price_change = (prices[-1] - prices[-5]) / prices[-5]
        
        # Aggregate signed volume over the recent 10-second horizon
        volume_window = 10.0
        now = self.kernel.current_time
        recent_signed_volume = sum(
            qty for ts, qty in self._recent_volume_history if (now - ts) <= volume_window
        )
        
        # Calculate depth sums directly for RL Env features
        bid_sum = sum(level["size"] for level in depth_data["bids"])
        ask_sum = sum(level["size"] for level in depth_data["asks"])
        fill_rate = len(self._all_trades) / max(1.0, self.kernel.current_time)
        imbalance = (bid_sum - ask_sum) / max(1, bid_sum + ask_sum)
=======
>>>>>>> upstream/main

        return {
            "current_time": self.current_time,
            "mid_price": self.order_book.mid_price or self.current_price,
            "best_bid": self.order_book.best_bid,
            "best_ask": self.order_book.best_ask,
            "spread": self.order_book.spread or 0.0,
<<<<<<< HEAD
            "bid_depth": bid_sum,
            "ask_depth": ask_sum,
            "order_book_imbalance": imbalance,
            "recent_signed_volume": recent_signed_volume,
            "recent_price_change": recent_price_change,
            "fill_rate": fill_rate,
            "total_depth": total_depth,
            "current_price": self.current_price,
            "time_to_close": max(0, self.duration_seconds - self.kernel.current_time),
=======
            "bid_depth": depth_data["bids"],
            "ask_depth": depth_data["asks"],
            "total_depth": total_depth,
            "current_price": self.current_price,
            "time_to_close": max(0, self.duration_seconds - self.current_time),
>>>>>>> upstream/main
            "volatility": volatility,
            "agents": {
                agent.agent_id: {
                    "type": agent.agent_type,
                    "position": agent.position,
                    "inventory_ratio": (
                        abs(agent.position) / 5000 if hasattr(agent, "max_inventory") else 0
                    ),
                }
                for agent in self.agents
            },
            "step": self.step_count,
        }

    def get_results(self) -> Dict:
        """Return final simulation results."""
        agent_metrics = {}
        for agent in self.agents:
            agent_metrics[agent.agent_id] = agent.get_metrics(self.current_price)

        return {
            "final_price": self.current_price,
            "initial_price": self.initial_price,
            "total_trades": len(self._all_trades),
            "total_steps": self.step_count,
            "price_history": list(self._price_history),
            "agent_metrics": agent_metrics,
        }

    def _compute_volatility(self) -> float:
        """Compute annualised volatility from recent log returns."""
        prices = list(self._price_history)
        if len(prices) < 20:
            return 0.0

        window = prices[-20:]
        log_returns = []
        for i in range(1, len(window)):
            if window[i] > 0 and window[i - 1] > 0:
                log_returns.append(math.log(window[i] / window[i - 1]))

        if len(log_returns) < 2:
            return 0.0

        mean_ret = sum(log_returns) / len(log_returns)
        variance = sum((r - mean_ret) ** 2 for r in log_returns) / (len(log_returns) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0

        # Annualise: sqrt(252 trading days * 390 minutes/day)
        return std * math.sqrt(252 * 390)

    def stop(self) -> None:
        """Stop the simulation loop."""
        self.running = False
        logger.info("Simulation stopped")
