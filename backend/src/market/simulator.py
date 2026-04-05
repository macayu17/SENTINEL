"""Market simulator — orchestrates agents, order book, and state tracking using a discrete event kernel."""

from typing import List, Dict, Optional, Any
import math
import random
from collections import deque
from .order_book import OrderBook
from .order import Order, OrderStatus
from .trade import Trade
from .kernel import EventKernel, EventType
from ..agents.base_agent import BaseAgent
from ..utils.logger import get_logger

logger = get_logger("simulator")


class MarketSimulator:
    """
    Multi-agent market microstructure simulator powered by an Event Kernel.

    Agents wake up according to latency-aware scheduling, submit orders,
    and receive delayed execution reports. The simulator also tracks
    recent activity for dashboard streaming.
    """

    def __init__(
        self,
        agents: List[BaseAgent],
        initial_price: float = 100.0,
        duration_seconds: int = 23_400,
        mode: str = "SANDBOX",
    ) -> None:
        self.agents = sorted(agents, key=lambda a: a.latency_seconds)
        self.order_book = OrderBook()
        self.kernel = EventKernel()
        self.initial_price = initial_price
        self.duration_seconds = duration_seconds

        self.current_price: float = initial_price
        self.step_count: int = 0
        self.running: bool = False
        self.mode: str = mode

        self._price_history: deque[float] = deque(maxlen=500)
        self._price_history.append(initial_price)
        self._state_history: List[Dict[str, Any]] = []
        self._all_trades: List[Trade] = []

        self._recent_volume_history: deque[tuple[float, float]] = deque(maxlen=100)

        self._recent_events: deque[Dict[str, Any]] = deque(maxlen=200)
        self._recent_orders: deque[Dict[str, Any]] = deque(maxlen=200)
        self._recent_trades: deque[Dict[str, Any]] = deque(maxlen=200)
        self._agent_actions: Dict[str, str] = {}

    @property
    def current_time(self) -> float:
        return self.kernel.current_time

    def _record_event(
        self,
        event_type: str,
        message: str,
        severity: str = "info",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._recent_events.append(
            {
                "ts": self.kernel.current_time,
                "type": event_type,
                "severity": severity,
                "message": message,
                "metadata": metadata or {},
            }
        )

    def _set_agent_action(self, agent: BaseAgent, message: str) -> None:
        self._agent_actions[agent.agent_id] = message

    def reset(self, seed: Optional[int] = None) -> Dict[str, Any]:
        """Reset the simulator for a new episode."""
        if seed is not None:
            random.seed(seed)
            try:
                import numpy as np

                np.random.seed(seed)
            except Exception:
                pass

        self.order_book = OrderBook()
        self.kernel.clear()
        self.current_price = self.initial_price
        self.step_count = 0
        self.running = False

        self._price_history.clear()
        self._price_history.append(self.initial_price)
        self._state_history.clear()
        self._all_trades.clear()
        self._recent_volume_history.clear()
        self._recent_events.clear()
        self._recent_orders.clear()
        self._recent_trades.clear()
        self._agent_actions.clear()

        self._seed_order_book()

        for agent in self.agents:
            if hasattr(agent, "reset"):
                agent.reset()
            else:
                agent.position = 0
                agent.realized_pnl = 0.0

            if getattr(agent, "agent_type", "") != "RL_MM":
                first_wake = random.uniform(0.01, 1.0)
                self.kernel.schedule(first_wake, EventType.WAKEUP, self._agent_wakeup, agent)

        self._record_event("Kernel", "Simulation reset and agents scheduled")
        return self.get_market_state()

    def _seed_order_book(self) -> None:
        """Place initial resting orders to bootstrap the book."""
        from .order import OrderSide, OrderType

        for i in range(10):
            offset = (i + 1) * 0.01
            bid = Order(
                agent_id="SEED",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=round(self.initial_price - offset, 2),
                quantity=500,
            )
            ask = Order(
                agent_id="SEED",
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                price=round(self.initial_price + offset, 2),
                quantity=500,
            )
            self.order_book.add_order(bid)
            self.order_book.add_order(ask)

    def _process_order(self, order: Order) -> None:
        """Exchange receives and processes an order."""
        order_payload = {
            "ts": self.kernel.current_time,
            "order_id": order.order_id,
            "agent_id": order.agent_id,
            "side": order.side.value.upper(),
            "order_type": order.order_type.value.upper(),
            "price": float(order.price),
            "quantity": int(order.quantity),
            "status": "Submitted",
        }
        self._recent_orders.append(order_payload)
        self._record_event(
            "Order Submission",
            f"{order.agent_id} submitted {order.side.value.upper()} {order.quantity}@{order.price:.2f}",
        )

        if self.mode != "SANDBOX":
            return

        trades = self.order_book.add_order(order)
        if trades:
            self._record_event("Order Match", f"{len(trades)} match(es) at step {self.step_count}")

        for trade in trades:
            self._all_trades.append(trade)
            self.current_price = trade.price
            self._price_history.append(self.current_price)

            signed_qty = (
                trade.quantity
                if trade.buyer_agent_id != "SEED"
                else -trade.quantity
            )
            self._recent_volume_history.append((self.kernel.current_time, signed_qty))

            self._recent_trades.append(
                {
                    "ts": self.kernel.current_time,
                    "trade_id": trade.trade_id,
                    "price": float(trade.price),
                    "quantity": int(trade.quantity),
                    "buyer_agent_id": trade.buyer_agent_id,
                    "seller_agent_id": trade.seller_agent_id,
                    "aggressor_side": "BUY"
                    if order.side.value == "buy"
                    else "SELL",
                }
            )
            self._record_event(
                "Fill",
                f"{trade.quantity} filled at {trade.price:.2f} ({trade.buyer_agent_id} vs {trade.seller_agent_id})",
            )

            for agent in self.agents:
                if agent.agent_id in (trade.buyer_agent_id, trade.seller_agent_id):
                    self.kernel.schedule(
                        agent.latency_seconds,
                        EventType.MARKET_DATA,
                        agent.update_position,
                        trade,
                    )

        if order.status == OrderStatus.CANCELLED:
            self._record_event(
                "Cancellation",
                f"Unfilled remainder cancelled for order {order.order_id}",
                severity="warning",
            )

    def _agent_wakeup(self, agent: BaseAgent) -> None:
        """Trigger an agent to observe market state and issue orders."""
        if not self.running:
            return

        try:
            state = self.get_market_state()
            orders = agent.decide_action(state)

            if orders:
                buy_count = sum(1 for o in orders if o.side.value == "buy")
                sell_count = len(orders) - buy_count
                self._set_agent_action(
                    agent,
                    f"Submitted {len(orders)} orders ({buy_count} buy / {sell_count} sell)",
                )
            else:
                self._set_agent_action(agent, "No action this wakeup")

            for order in orders:
                if agent.latency_seconds >= 0.01:
                    self._record_event(
                        "Latency",
                        f"{agent.agent_id} order delayed by {agent.latency_seconds * 1000:.1f} ms",
                    )
                self.kernel.schedule(
                    agent.latency_seconds,
                    EventType.ORDER_ARRIVAL,
                    self._process_order,
                    order,
                )
        except Exception as exc:
            logger.error(f"Agent {agent.agent_id} error: {exc}")
            self._record_event(
                "Kernel",
                f"Agent error for {agent.agent_id}: {exc}",
                severity="critical",
            )

        interval = getattr(agent, "wakeup_interval", 1.0)
        jitter = random.uniform(0.9, 1.1)
        self.kernel.schedule(interval * jitter, EventType.WAKEUP, self._agent_wakeup, agent)

    def run(self, steps: Optional[int] = None) -> Dict[str, Any]:
        """Run synchronously for legacy scripts and tests."""
        self.reset()
        self.running = True
        target_time = float(steps if steps is not None else self.duration_seconds)

        logger.info(f"Starting kernel event loop until T={target_time}s")
        self.kernel.run_until(target_time)
        self.running = False
        self.step_count = int(self.kernel.current_time)
        return self.get_results()

    def step(self) -> Dict[str, Any]:
        """Advance simulator by one second equivalent."""
        if not self.running:
            self.running = True

        self.step_count += 1
        target = self.kernel.current_time + 1.0
        self.kernel.run_until(target)

        state = self.get_market_state()
        self._state_history.append(state)
        return state

    def get_market_state(self) -> Dict[str, Any]:
        """Return current market state snapshot."""
        depth_data = self.order_book.get_depth(levels=10)
        total_depth = self.order_book.get_total_depth(levels=10)
        volatility = self._compute_volatility()

        prices = list(self._price_history)
        recent_price_change = 0.0
        if len(prices) >= 5 and prices[-5] > 0:
            recent_price_change = (prices[-1] - prices[-5]) / prices[-5]

        now = self.kernel.current_time
        recent_signed_volume = sum(
            qty for ts, qty in self._recent_volume_history if (now - ts) <= 10.0
        )

        bid_sum = sum(level["size"] for level in depth_data["bids"])
        ask_sum = sum(level["size"] for level in depth_data["asks"])
        fill_rate = len(self._all_trades) / max(1.0, self.kernel.current_time)
        imbalance = (bid_sum - ask_sum) / max(1, bid_sum + ask_sum)

        return {
            "current_time": self.current_time,
            "mid_price": self.order_book.mid_price or self.current_price,
            "best_bid": self.order_book.best_bid,
            "best_ask": self.order_book.best_ask,
            "spread": self.order_book.spread or 0.0,
            "bid_depth": bid_sum,
            "ask_depth": ask_sum,
            "order_book_imbalance": imbalance,
            "recent_signed_volume": recent_signed_volume,
            "recent_price_change": recent_price_change,
            "fill_rate": fill_rate,
            "total_depth": total_depth,
            "current_price": self.current_price,
            "time_to_close": max(0.0, self.duration_seconds - self.kernel.current_time),
            "volatility": volatility,
            "order_book_levels": depth_data,
            "agents": {
                agent.agent_id: {
                    "type": agent.agent_type,
                    "position": agent.position,
                    "inventory_ratio": (
                        abs(agent.position) / 5000 if hasattr(agent, "max_inventory") else 0.0
                    ),
                }
                for agent in self.agents
            },
            "step": self.step_count,
        }

    def get_recent_activity(self, limit: int = 20) -> Dict[str, Any]:
        """Return recent events, orders, trades, and latest agent actions."""

        def latest(items: deque[Dict[str, Any]]) -> List[Dict[str, Any]]:
            sliced = list(items)[-limit:]
            return list(reversed(sliced))

        return {
            "events": latest(self._recent_events),
            "orders": latest(self._recent_orders),
            "trades": latest(self._recent_trades),
            "agent_actions": self._agent_actions,
        }

    def get_results(self) -> Dict[str, Any]:
        """Return final simulation results."""
        agent_metrics = {
            agent.agent_id: agent.get_metrics(self.current_price) for agent in self.agents
        }

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

        return std * math.sqrt(252 * 390)

    def stop(self) -> None:
        """Stop the simulation loop."""
        self.running = False
        logger.info("Simulation stopped")
