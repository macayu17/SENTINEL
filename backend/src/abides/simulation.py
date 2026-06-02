"""ABIDES-style simulation orchestrator."""

from __future__ import annotations

from collections import deque
from itertools import islice
from typing import Any, Dict, List, Optional, Sequence

from .kernel import EventKernel, EventType
from .messages import Message, OrderMessage, CancelMessage, MarketDataMessage, TradeMessage
from .agents.base import Agent
from .agents.exchange import ExchangeAgent
from ..market.latency_model import LatencyModel, LatencyConfig
from ..market.oracle import MeanRevertingOracle, OracleConfig
from ..market.order import OrderSide


class AbidesSimulation:
    def __init__(
        self,
        oracle_config: Optional[OracleConfig] = None,
        latency_config: Optional[LatencyConfig] = None,
        speed_multiplier: float = 1.0,
    ) -> None:
        self.kernel = EventKernel()
        self.agents: Dict[str, Agent] = {}
        self.exchange: Optional[ExchangeAgent] = None
        self.oracle = MeanRevertingOracle(oracle_config)
        self.latency_model = LatencyModel(latency_config)
        self.speed_multiplier = speed_multiplier if speed_multiplier > 0 else 1.0
        self._last_oracle_time: float = 0.0
        self.running: bool = False
        self.step_count: int = 0
        self._submitted_order_count: int = 0
        self._cancel_request_count: int = 0
        self._buy_volume: int = 0
        self._sell_volume: int = 0
        self._event_sequence: int = 0
        self._event_log: deque[Dict[str, Any]] = deque(maxlen=500)
        self._recent_orders: deque[Dict[str, Any]] = deque(maxlen=200)

    def set_exchange(self, exchange: ExchangeAgent) -> None:
        self.exchange = exchange
        exchange.bind(self.kernel, self)
        for agent in self.agents.values():
            agent.last_mid = exchange.last_price

    def register_agent(self, agent: Agent) -> None:
        self.agents[agent.agent_id] = agent
        agent.bind(self.kernel, self)
        if self.exchange is not None:
            agent.last_mid = self.exchange.last_price

    def initialize(self) -> None:
        if self.exchange is None:
            raise RuntimeError("Exchange agent is not configured")
        self._last_oracle_time = self.kernel.current_time
        self.running = True
        self.step_count = 0
        self._submitted_order_count = 0
        self._cancel_request_count = 0
        self._buy_volume = 0
        self._sell_volume = 0
        self._event_sequence = 0
        self._event_log.clear()
        self._recent_orders.clear()
        for agent in self.agents.values():
            agent.on_start()
        self._broadcast_market_data()
        for agent in self.agents.values():
            self.kernel.schedule_in(agent.wakeup_interval, EventType.WAKEUP, self._agent_wakeup, agent.agent_id)

    def run(self, duration_seconds: float) -> None:
        self.initialize()
        self.kernel.run_until(self.kernel.current_time + duration_seconds)
        self.running = False

    def step(self, step_seconds: float = 1.0) -> Dict:
        if not self.running:
            self.initialize()
        target = self.kernel.current_time + max(0.001, step_seconds)
        self.kernel.run_until(target)
        self.step_count += 1
        return self.get_state()

    def get_state(self) -> Dict:
        if self.exchange is None:
            return {}
        book = self.exchange.order_book
        total_depth, bid_levels, ask_levels = book.get_depth_snapshot(10)
        mid = book.mid_price or self.exchange.last_price
        price = self.exchange.last_price or mid
        return {
            "current_time": self.kernel.current_time,
            "price": price,
            "mid_price": mid,
            "spread": book.spread,
            "best_bid": book.best_bid,
            "best_ask": book.best_ask,
            "total_depth": total_depth,
            "bid_levels": bid_levels,
            "ask_levels": ask_levels,
            "step": self.step_count,
            "oracle": self.oracle.get_mispricing(price) if self.oracle.enabled else None,
        }

    def _agent_wakeup(self, agent_id: str) -> None:
        agent = self.agents.get(agent_id)
        if agent is None:
            return
        self._advance_oracle()
        outbound = agent.on_wakeup(self.kernel.current_time)
        for msg in outbound:
            self._dispatch_message(msg)
        self.kernel.schedule_in(agent.wakeup_interval, EventType.WAKEUP, self._agent_wakeup, agent_id)

    def _dispatch_message(self, message: Message) -> None:
        if self.exchange is None:
            return
        if isinstance(message, OrderMessage):
            self._record_order_submission(message)
            self._schedule_exchange_message(message)
            return

        if isinstance(message, CancelMessage):
            self._record_cancel_request(message)
            self._schedule_exchange_message(message)
            return

        self.kernel.schedule_in(0.0, EventType.MESSAGE, self._deliver_to_agent, message)

    def _deliver_to_exchange(self, message: Message) -> None:
        if self.exchange is None:
            return
        self._advance_oracle()
        outbound = self.exchange.on_message(message, self.kernel.current_time)
        for msg in outbound:
            if isinstance(msg, TradeMessage):
                aggressor_side = message.side if isinstance(message, OrderMessage) else None
                self._record_fill(msg, aggressor_side=aggressor_side)
                self._schedule_agent_message(msg.recipient_id or "", msg)
            else:
                self._deliver_to_agent(msg)

    def _deliver_to_agent(self, message: Message) -> None:
        if isinstance(message, MarketDataMessage):
            oracle_info = message.oracle
            if oracle_info is None and self.oracle.enabled and self.exchange is not None:
                mark = self.exchange.last_price or message.mid_price
                oracle_info = self.oracle.get_mispricing(mark)
            for agent in self.agents.values():
                delay = self._get_agent_latency(agent.agent_id)
                payload = MarketDataMessage(
                    sender_id=message.sender_id,
                    mid_price=message.mid_price,
                    best_bid=message.best_bid,
                    best_ask=message.best_ask,
                    spread=message.spread,
                    oracle=oracle_info,
                    timestamp=message.timestamp,
                )
                self.kernel.schedule_in(
                    self._scale_delay(delay),
                    EventType.MESSAGE,
                    self._deliver_market_data,
                    (agent.agent_id, payload),
                )
            return

        recipient = self.agents.get(message.recipient_id or "")
        if recipient:
            recipient.on_message(message)

    def _broadcast_market_data(self) -> None:
        if self.exchange is None:
            return
        mid = self.exchange.order_book.mid_price or self.exchange.last_price
        oracle_info = self.oracle.get_mispricing(self.exchange.last_price) if self.oracle.enabled else None
        for agent in self.agents.values():
            agent.on_message(
                MarketDataMessage(
                    sender_id=self.exchange.exchange_id,
                    mid_price=mid,
                    best_bid=self.exchange.order_book.best_bid,
                    best_ask=self.exchange.order_book.best_ask,
                    spread=self.exchange.order_book.spread,
                    oracle=oracle_info,
                    timestamp=self.kernel.current_time,
                )
            )

    def _deliver_market_data(self, payload: tuple[str, MarketDataMessage]) -> None:
        agent_id, message = payload
        agent = self.agents.get(agent_id)
        if agent:
            agent.on_message(message)

    def _schedule_exchange_message(self, message: Message) -> None:
        delay = self._get_agent_latency(message.sender_id)
        self.kernel.schedule_in(
            self._scale_delay(delay),
            EventType.MESSAGE,
            self._deliver_to_exchange,
            message,
        )

    def _schedule_agent_message(self, agent_id: str, message: Message) -> None:
        delay = self._get_agent_latency(agent_id)
        self.kernel.schedule_in(
            self._scale_delay(delay),
            EventType.MESSAGE,
            self._deliver_to_agent,
            message,
        )

    def _advance_oracle(self) -> None:
        if not self.oracle.enabled:
            return
        now = self.kernel.current_time
        dt = max(0.0, now - self._last_oracle_time)
        if dt <= 0:
            return
        self.oracle.advance(dt=dt)
        self._last_oracle_time = now

    def _get_agent_latency(self, agent_id: str) -> float:
        agent = self.agents.get(agent_id)
        if agent is None:
            return 0.0
        if agent.latency_seconds > 0:
            return agent.latency_seconds
        return self.latency_model.get_latency(agent.agent_type)

    def _scale_delay(self, delay: float) -> float:
        if delay <= 0:
            return 0.0
        return delay / self.speed_multiplier

    def _agent_type_for(self, agent_id: str) -> str:
        agent = self.agents.get(agent_id)
        return agent.agent_type if agent else "External"

    def _record_order_submission(self, message: OrderMessage) -> None:
        self._submitted_order_count += 1
        side = message.side.value.upper()
        self._record_recent_order(
            agent_id=message.sender_id,
            side=side,
            price=message.price,
            quantity=message.quantity,
            status="submitted",
        )
        self._record_event(
            "order_submission",
            f"{message.sender_id} submitted {side} order",
            agent_id=message.sender_id,
            side=side,
            price=message.price,
            quantity=message.quantity,
            status="submitted",
        )

    def _record_cancel_request(self, message: CancelMessage) -> None:
        self._cancel_request_count += 1
        self._record_event(
            "cancellation",
            f"{message.sender_id} requested cancellation",
            agent_id=message.sender_id,
            order_id=message.order_id,
            status="cancelled",
        )

    def _record_fill(self, message: TradeMessage, aggressor_side: Optional[OrderSide] = None) -> None:
        if message.recipient_id != message.buyer_id:
            return
        side = aggressor_side or OrderSide.BUY
        if side == OrderSide.SELL:
            self._sell_volume += message.quantity
            agent_id = message.seller_id
        else:
            self._buy_volume += message.quantity
            agent_id = message.buyer_id
        self._record_recent_order(
            agent_id=agent_id,
            side=side.value.upper(),
            price=message.price,
            quantity=message.quantity,
            status="filled",
        )
        self._record_event(
            "fill",
            f"ABIDES filled {message.quantity} @ {message.price:.2f}",
            agent_id=agent_id,
            side=side.value.upper(),
            price=message.price,
            quantity=message.quantity,
            status="filled",
        )

    def _record_event(
        self,
        event_type: str,
        message: str,
        *,
        severity: str = "info",
        agent_id: Optional[str] = None,
        order_id: Optional[str] = None,
        side: Optional[str] = None,
        price: Optional[float] = None,
        quantity: Optional[int] = None,
        status: Optional[str] = None,
    ) -> None:
        self._event_sequence += 1
        event: Dict[str, Any] = {
            "id": f"ab-ev-{self._event_sequence}",
            "timestamp": round(float(self.kernel.current_time), 6),
            "step": self.step_count,
            "type": event_type,
            "severity": severity,
            "message": message,
        }
        optional_values = {
            "agent_id": agent_id,
            "agent_type": self._agent_type_for(agent_id) if agent_id else None,
            "order_id": order_id,
            "side": side,
            "price": round(float(price), 6) if price is not None else None,
            "quantity": int(quantity) if quantity is not None else None,
            "status": status,
        }
        for key, value in optional_values.items():
            if value is not None:
                event[key] = value
        self._event_log.append(event)

    def _record_recent_order(
        self,
        *,
        agent_id: str,
        side: str,
        price: float,
        quantity: int,
        status: str,
    ) -> None:
        self._recent_orders.append(
            {
                "id": f"AB-{self._event_sequence + 1}",
                "agent_id": agent_id,
                "agent_type": self._agent_type_for(agent_id),
                "side": side,
                "price": round(float(price), 6),
                "quantity": int(quantity),
                "status": status,
                "timestamp": round(float(self.kernel.current_time), 6),
            }
        )

    def _trades(self) -> Sequence[Any]:
        if self.exchange is None:
            return []
        book = getattr(self.exchange.order_book, "_book", None)
        return getattr(book, "trades", []) or []

    @staticmethod
    def _latest(items: deque[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        return list(islice(reversed(items), max(0, limit)))

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._latest(self._event_log, limit)

    def get_recent_orders(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._latest(self._recent_orders, limit)

    def get_order_flow_summary(self, trades: Optional[Sequence[Any]] = None) -> Dict[str, Any]:
        trade_history = trades if trades is not None else self._trades()
        fills = len(trade_history)
        match_rate = (fills / self._submitted_order_count) * 100 if self._submitted_order_count else 0.0
        return {
            "submitted": self._submitted_order_count,
            "fills": fills,
            "cancelled": self._cancel_request_count,
            "match_rate": round(match_rate, 2),
            "buy_volume": self._buy_volume,
            "sell_volume": self._sell_volume,
        }

    def get_export_snapshot(self, warning_timeline: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        state = self.get_state()
        current_price = state.get("price") or state.get("mid_price") or 0.0
        trades = self._trades()
        return {
            "run_config": {
                "engine": "ABIDES",
                "mode": "SANDBOX",
                "speed": self.speed_multiplier,
                "oracle_enabled": self.oracle.enabled,
            },
            "state": state,
            "order_flow": {
                "summary": self.get_order_flow_summary(trades),
                "trades": [
                    {
                        "price": trade.price,
                        "quantity": trade.quantity,
                        "buyer_agent_id": trade.buyer_agent_id,
                        "seller_agent_id": trade.seller_agent_id,
                    }
                    for trade in trades
                ],
            },
            "events": self.get_recent_events(limit=500),
            "recent_orders": self.get_recent_orders(limit=200),
            "agent_metrics": {
                agent.agent_id: agent.get_metrics(current_price)
                for agent in self.agents.values()
            },
            "warning_timeline": list(warning_timeline or []),
        }
