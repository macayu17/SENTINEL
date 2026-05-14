"""ABIDES-style simulation orchestrator."""

from __future__ import annotations

from typing import Dict, Optional

from .kernel import EventKernel, EventType
from .messages import Message, OrderMessage, CancelMessage, MarketDataMessage, TradeMessage
from .agents.base import Agent
from .agents.exchange import ExchangeAgent
from ..market.latency_model import LatencyModel, LatencyConfig
from ..market.oracle import MeanRevertingOracle, OracleConfig


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
        for agent in self.agents.values():
            agent.on_start()
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
        mid = self.exchange.order_book.mid_price or self.exchange.last_price
        return {
            "current_time": self.kernel.current_time,
            "price": self.exchange.last_price or mid,
            "mid_price": mid,
            "spread": self.exchange.order_book.spread,
            "best_bid": self.exchange.order_book.best_bid,
            "best_ask": self.exchange.order_book.best_ask,
            "total_depth": self.exchange.order_book.get_total_depth(10),
            "bid_levels": self.exchange.order_book.bid_levels,
            "ask_levels": self.exchange.order_book.ask_levels,
            "step": self.step_count,
            "oracle": self.oracle.get_mispricing(self.exchange.last_price or mid) if self.oracle.enabled else None,
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
        if isinstance(message, (OrderMessage, CancelMessage)):
            delay = self._get_agent_latency(message.sender_id)
            self.kernel.schedule_in(self._scale_delay(delay), EventType.MESSAGE, self._deliver_to_exchange, message)
        else:
            self.kernel.schedule_in(0.0, EventType.MESSAGE, self._deliver_to_agent, message)

    def _deliver_to_exchange(self, message: Message) -> None:
        if self.exchange is None:
            return
        self._advance_oracle()
        outbound = self.exchange.on_message(message, self.kernel.current_time)
        for msg in outbound:
            if isinstance(msg, TradeMessage):
                delay = self._get_agent_latency(msg.recipient_id)
                self.kernel.schedule_in(self._scale_delay(delay), EventType.MESSAGE, self._deliver_to_agent, msg)
            else:
                self._deliver_to_agent(msg)

    def _deliver_to_agent(self, message: Message) -> None:
        if isinstance(message, MarketDataMessage):
            oracle_info = None
            if self.oracle.enabled:
                oracle_info = self.oracle.get_mispricing(self.exchange.last_price if self.exchange else 0.0)

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

        if isinstance(message, TradeMessage):
            recipient = self.agents.get(message.recipient_id or "")
            if recipient:
                recipient.on_message(message)
            return

        recipient = self.agents.get(message.recipient_id or "")
        if recipient:
            recipient.on_message(message)

    def _deliver_market_data(self, payload: tuple[str, MarketDataMessage]) -> None:
        agent_id, message = payload
        agent = self.agents.get(agent_id)
        if agent:
            agent.on_message(message)

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
