"""Market simulator — orchestrates agents, order book, and state tracking using a discrete event kernel."""

from typing import Any, Dict, List, Optional
from dataclasses import replace
import math
import random
from collections import deque

from .kernel import EventKernel, EventType
from .order_book import OrderBook
from .order import RESTING_ORDER_TYPES, Order, OrderSide, OrderType, OrderStatus
from .trade import Trade
from .oracle import MeanRevertingOracle, OracleConfig
from .latency_model import LatencyModel, LatencyConfig, LatencyMode
from .scenario import ScenarioConfig, apply_scenario_agent_counts, get_scenario_config
from ..agents.base_agent import BaseAgent
from ..agents.risk import enforce_trading_rules
from ..utils.logger import get_logger

logger = get_logger("simulator")

# Venue-internal delay between a stop being breached and its market order arriving.
STOP_TRIGGER_LATENCY_SECONDS = 0.0005
LIQUIDITY_SHOCK_TRIGGER_FRACTION = 0.35
LIQUIDITY_SHOCK_RECOVERY_UPDATES = 20.0
LIQUIDITY_SHOCK_PRIMARY_WITHDRAWAL = 0.65
LIQUIDITY_SHOCK_SECONDARY_WITHDRAWAL = 0.35
LIQUIDITY_SHOCK_SWEEP_FRACTION = 0.40


class MarketSimulator:
    """
    Multi-agent market microstructure simulator powered by an event kernel.

    Agents wake up asynchronously, generate orders based on the latest market
    snapshot, and those orders arrive at the exchange after each agent's
    structural latency. The simulator tracks both order-book state and the
    richer metrics consumed by the API, predictors, and RL environment.
    """

    def __init__(
        self,
        agents: List[BaseAgent],
        initial_price: float = 100.0,
        duration_seconds: int = 23_400,
        mode: str = "SANDBOX",
        order_ttl_seconds: Optional[float] = None,
        oracle_config: Optional[OracleConfig] = None,
        latency_config: Optional[LatencyConfig] = None,
        speed_multiplier: float = 1.0,
        scenario: str | ScenarioConfig = "normal",
        depth_profile: Optional[Dict[str, Any]] = None,
        informed_oracle_access: Optional[bool] = None,
        seed: Optional[int] = None,
        venue: str = "NASDAQ",
    ) -> None:
        self.agents = sorted(agents, key=lambda agent: agent.latency_seconds)
        self._agents_by_id: Dict[str, BaseAgent] = {}
        self._index_agents()
        self.order_book = OrderBook()
        self.kernel = EventKernel()
        self.initial_price = initial_price
        self.duration_seconds = duration_seconds
        self.mode = mode
        self.speed_multiplier = speed_multiplier
        self.venue = venue
        self.scenario = scenario if isinstance(scenario, ScenarioConfig) else get_scenario_config(scenario)
        self.order_ttl_seconds = float(
            self.scenario.order_ttl_seconds if order_ttl_seconds is None else order_ttl_seconds
        )
        self.depth_profile: Dict[str, Any] = depth_profile or {}

        # Oracle & latency
        self.oracle = MeanRevertingOracle(oracle_config)
        self.informed_oracle_access = (
            self.oracle.enabled
            if informed_oracle_access is None
            else bool(informed_oracle_access)
        )
        self.latency_model = LatencyModel(latency_config)

        self.current_price: float = initial_price
        self.step_count: int = 0
        self.running: bool = False
        self._price_history: deque[float] = deque(maxlen=1_000)
        self._state_history: List[Dict] = []
        self._all_trades: List[Trade] = []
        self._recent_volume_history: deque[tuple[float, int]] = deque(maxlen=2_000)
        self._submitted_order_count: int = 0
        self._matched_order_count: int = 0
        self._cancel_request_count: int = 0
        self._accepted_cancel_count: int = 0
        self._terminal_cancel_count: int = 0
        self._submitted_notional: float = 0.0
        self._slippage_bps_samples: List[float] = []
        self._event_sequence: int = 0
        self._event_log: deque[Dict[str, Any]] = deque(maxlen=500)
        self._recent_orders: deque[Dict[str, Any]] = deque(maxlen=200)
        self._resting_stops: List[Order] = []
        self._scenario_events_triggered: set[str] = set()
        self._liquidity_shock_side: Optional[OrderSide] = None
        self._liquidity_shock_trigger_time: Optional[float] = None
        self._liquidity_shock_baseline_depth: int = 0
        self._liquidity_shock_baseline_spread: float = 0.0
        self._last_session_phase: str = "PREOPEN"
        self.seed: Optional[int] = seed
        self.rng = random.Random(seed)

        self.reset(seed=seed)

    def _index_agents(self) -> None:
        self._agents_by_id.clear()
        for agent in self.agents:
            self._agents_by_id.setdefault(agent.agent_id, agent)

    @property
    def current_time(self) -> float:
        return self.kernel.current_time

    def reset(self, seed: Optional[int] = None) -> Dict:
        """Reset the simulator for a new episode and return the initial state."""
        self._index_agents()
        effective_seed = self.seed if seed is None else seed
        if effective_seed is not None:
            self.seed = effective_seed
            self.rng.seed(effective_seed)

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
        self._submitted_order_count = 0
        self._matched_order_count = 0
        self._cancel_request_count = 0
        self._accepted_cancel_count = 0
        self._terminal_cancel_count = 0
        self._submitted_notional = 0.0
        self._slippage_bps_samples.clear()
        self._event_sequence = 0
        self._event_log.clear()
        self._recent_orders.clear()
        self._resting_stops.clear()
        self._scenario_events_triggered.clear()
        self._liquidity_shock_side = (
            self.rng.choice((OrderSide.BUY, OrderSide.SELL))
            if self.scenario.name == "liquidity_shock"
            else None
        )
        self._liquidity_shock_trigger_time = None
        self._liquidity_shock_baseline_depth = 0
        self._liquidity_shock_baseline_spread = 0.0
        self._last_session_phase = self._session_profile()[0]
        self.latency_model.reset(effective_seed)
        self.oracle.reset(effective_seed)

        self._seed_order_book()
        self._liquidity_shock_baseline_depth = self.order_book.get_total_depth(levels=10)
        self._liquidity_shock_baseline_spread = float(self.order_book.spread or 0.0)

        for agent in self.agents:
            agent.reset()

            if getattr(agent, "external_action_controlled", False):
                continue

            first_wake = self.rng.uniform(0.01, 1.0)
            self.kernel.schedule(first_wake, EventType.WAKEUP, self._agent_wakeup, agent)

        return self.get_market_state()

    def _seed_order_book(self, anchor: Optional[float] = None) -> None:
        """Place initial resting orders to bootstrap the book."""
        reference_price = self.initial_price if anchor is None else anchor
        levels = int(self.depth_profile.get("levels", 10) or 10)
        tick_spacing = float(self.depth_profile.get("tick_spacing", 0.01) or 0.01)
        level_size = int(
            self.depth_profile.get(
                "level_size",
                max(1, round(500 * self.scenario.seed_depth_multiplier)),
            )
        )
        spread_multiplier = float(self.depth_profile.get("spread_multiplier", self.scenario.spread_multiplier) or 1.0)
        for i in range(max(1, min(20, levels))):
            offset = (i + 1) * tick_spacing * spread_multiplier
            bid = Order(
                agent_id="SEED",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=round(reference_price - offset, 2),
                quantity=level_size,
            )
            ask = Order(
                agent_id="SEED",
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                price=round(reference_price + offset, 2),
                quantity=level_size,
            )
            self.order_book.add_order(bid)
            self.order_book.add_order(ask)

    def _ensure_liquidity_floor(self) -> None:
        """Replenish thin books so the dashboard demo remains two-sided and responsive."""
        floor_multiplier = self.scenario.liquidity_floor_multiplier
        spread_multiplier = self.scenario.spread_multiplier
        refill_levels = 5
        shock_phase = "ACTIVE"
        if self.scenario.name == "liquidity_shock":
            shock_phase, _ = self._liquidity_shock_state()
            floor_multiplier, spread_multiplier, refill_levels = (
                self._liquidity_provision_profile()
            )
        total_depth = self.order_book.get_total_depth(levels=10)
        depth_floor = max(100, int(600 * floor_multiplier))
        if self.scenario.name == "liquidity_shock":
            depth_floor = max(
                depth_floor,
                int(self._liquidity_shock_baseline_depth * floor_multiplier),
            )
        max_healthy_spread = 0.04 * spread_multiplier
        if self.scenario.name == "liquidity_shock":
            max_healthy_spread = max(
                0.01,
                self._liquidity_shock_baseline_spread * spread_multiplier,
            )
        if (
            self.order_book.best_bid is not None
            and self.order_book.best_ask is not None
            and total_depth >= depth_floor
            and (self.order_book.spread or 0.0) <= max_healthy_spread
        ):
            return

        anchor = round(
            self.current_price or self.order_book.mid_price or self.initial_price,
            2,
        )
        tick_spacing = float(self.depth_profile.get("tick_spacing", 0.01) or 0.01)
        for i in range(refill_levels):
            offset = (i + 1) * tick_spacing * spread_multiplier
            quantity = max(25, int(150 * floor_multiplier))
            if shock_phase == "RECOVERY":
                depth_deficit = max(
                    0,
                    self._liquidity_shock_baseline_depth - total_depth,
                )
                quantity = max(quantity, int(depth_deficit * 0.08))
            bid = Order(
                agent_id="SEED",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=round(anchor - offset, 2),
                quantity=quantity,
            )
            ask = Order(
                agent_id="SEED",
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                price=round(anchor + offset, 2),
                quantity=quantity,
            )
            self.order_book.add_order(bid)
            self.order_book.add_order(ask)

    def _apply_scenario_driver(self) -> bool:
        """Apply explicit exogenous flow for scenarios that promise a market shock."""
        if self.scenario.name == "liquidity_shock":
            return self._apply_liquidity_shock()
        if self.scenario.name != "volatility_spike":
            return False

        first_trigger = min(60.0, max(1.0, self.duration_seconds * 0.35))
        second_trigger = min(120.0, max(first_trigger + 1.0, self.duration_seconds * 0.55))
        applied = False
        for key, trigger_time, side in (
            ("volatility_buy_impulse", first_trigger, OrderSide.BUY),
            ("volatility_sell_impulse", second_trigger, OrderSide.SELL),
        ):
            if self.current_time < trigger_time or key in self._scenario_events_triggered:
                continue
            self._scenario_events_triggered.add(key)
            self._sweep_scenario_flow(side)
            applied = True
        return applied

    def _liquidity_shock_trigger(self) -> float:
        return min(
            60.0,
            max(1.0, self.duration_seconds * LIQUIDITY_SHOCK_TRIGGER_FRACTION),
        )

    def _liquidity_shock_state(self) -> tuple[str, float]:
        if self.scenario.name != "liquidity_shock":
            return "ACTIVE", 1.0
        if self._liquidity_shock_trigger_time is None:
            return "WARMUP", 0.0
        elapsed = max(0.0, self.current_time - self._liquidity_shock_trigger_time)
        progress = min(1.0, elapsed / LIQUIDITY_SHOCK_RECOVERY_UPDATES)
        if elapsed < 1.0:
            return "IMPACT", progress
        if progress < 1.0:
            return "RECOVERY", progress
        return "NORMALIZED", 1.0

    def _liquidity_provision_profile(self) -> tuple[float, float, int]:
        phase, progress = self._liquidity_shock_state()
        if phase in {"WARMUP", "NORMALIZED"}:
            return 1.0, 1.0, 5
        if phase == "IMPACT":
            return 0.2, 3.0, 0
        return 0.2 + 0.8 * progress, 1.0 + 2.0 * (1.0 - progress), 1

    def _withdraw_liquidity(self, orders: List[Order], fraction: float) -> int:
        target = sum(order.displayed_quantity for order in orders) * fraction
        removed = 0
        for order in list(orders):
            visible = order.displayed_quantity
            if self._cancel_order(order.order_id, record_event=False):
                removed += visible
            if removed >= target:
                break
        return removed

    def _apply_liquidity_shock(self) -> bool:
        event_key = "liquidity_shock"
        if (
            self.current_time < self._liquidity_shock_trigger()
            or event_key in self._scenario_events_triggered
            or self._liquidity_shock_side is None
        ):
            return False

        self._scenario_events_triggered.add(event_key)
        self._liquidity_shock_trigger_time = self.current_time
        self._liquidity_shock_baseline_depth = self.order_book.get_total_depth(levels=10)
        self._liquidity_shock_baseline_spread = float(self.order_book.spread or 0.01)
        sweep_side = self._liquidity_shock_side
        primary_book = self.order_book.asks if sweep_side == OrderSide.BUY else self.order_book.bids
        secondary_book = self.order_book.bids if sweep_side == OrderSide.BUY else self.order_book.asks
        removed = self._withdraw_liquidity(
            primary_book, LIQUIDITY_SHOCK_PRIMARY_WITHDRAWAL
        )
        removed += self._withdraw_liquidity(
            secondary_book, LIQUIDITY_SHOCK_SECONDARY_WITHDRAWAL
        )
        side_label = sweep_side.value.upper()
        self._record_event(
            "liquidity_withdrawal",
            f"Liquidity providers withdrew {removed} shares before a {side_label} imbalance",
            severity="warning",
            agent_id="LIQUIDITY_SHOCK_FLOW",
            side=side_label,
            quantity=removed,
            status="withdrawn",
        )

        depth = self.order_book.get_depth(levels=10)
        opposite = depth["asks"] if sweep_side == OrderSide.BUY else depth["bids"]
        quantity = max(
            1,
            round(
                sum(int(level["size"]) for level in opposite)
                * LIQUIDITY_SHOCK_SWEEP_FRACTION
            ),
        )
        trades_before = len(self._all_trades)
        self._process_order(
            Order(
                agent_id="LIQUIDITY_SHOCK_FLOW",
                side=sweep_side,
                order_type=OrderType.MARKET,
                price=self.current_price,
                quantity=quantity,
            )
        )
        matched = sum(
            trade.quantity for trade in self._all_trades[trades_before:]
        )
        self._record_event(
            "liquidity_impact",
            f"Aggressive {side_label} flow consumed {matched} displayed shares",
            severity="critical",
            agent_id="LIQUIDITY_SHOCK_FLOW",
            side=side_label,
            quantity=matched,
            status="matched",
        )
        return True

    def _apply_reference_flow(self) -> bool:
        """Move the synthetic book toward its latent value through normal matching."""
        if (
            not self.oracle.enabled
            or self._session_profile()[0] in {"PREOPEN", "SQUAREOFF"}
        ):
            return False

        mid = self.order_book.mid_price
        spread = self.order_book.spread
        if mid is None or spread is None:
            return False

        gap = self.oracle.current_value - mid
        if abs(gap) < 0.01 + spread / 2:
            return False

        side = OrderSide.BUY if gap > 0 else OrderSide.SELL
        depth = self.order_book.get_depth(levels=1)
        levels = depth["asks"] if side == OrderSide.BUY else depth["bids"]
        if not levels:
            return False

        touch = levels[0]
        before = len(self._all_trades)
        self._process_order(
            Order(
                agent_id="REFERENCE_FLOW",
                side=side,
                order_type=OrderType.IOC,
                price=float(touch["price"]),
                quantity=max(1, int(touch["size"])),
            )
        )
        return len(self._all_trades) > before

    def _sweep_scenario_flow(self, side: OrderSide) -> None:
        depth = self.order_book.get_depth(levels=10)
        opposite_levels = depth["asks"] if side == OrderSide.BUY else depth["bids"]
        visible_depth = sum(int(level["size"]) for level in opposite_levels)
        quantity = max(1, round(visible_depth * 0.7))
        side_label = side.value.upper()
        self._record_event(
            "scenario_driver",
            f"Exogenous volatility impulse swept {quantity} shares {side_label}",
            severity="warning",
            agent_id="SCENARIO_FLOW",
            side=side_label,
            quantity=quantity,
            status="triggered",
        )
        self._process_order(
            Order(
                agent_id="SCENARIO_FLOW",
                side=side,
                order_type=OrderType.MARKET,
                price=self.current_price,
                quantity=quantity,
            )
        )

    def _agent_type_for(self, agent_id: str) -> str:
        agent = self.get_agent(agent_id)
        if agent is not None:
            return agent.agent_type
        if agent_id in {
            "SEED",
            "EXTERNAL_DEPTH",
            "REFERENCE_FLOW",
            "LIQUIDITY_SHOCK_FLOW",
        }:
            return agent_id
        return "External"

    def _record_event(
        self,
        event_type: str,
        message: str,
        *,
        severity: str = "info",
        agent_id: Optional[str] = None,
        order_id: Optional[str] = None,
        trade_id: Optional[str] = None,
        side: Optional[str] = None,
        price: Optional[float] = None,
        quantity: Optional[int] = None,
        status: Optional[str] = None,
    ) -> None:
        self._event_sequence += 1
        event: Dict[str, Any] = {
            "id": f"ev-{self._event_sequence}",
            "timestamp": round(float(self.current_time), 6),
            "step": self.step_count,
            "type": event_type,
            "severity": severity,
            "message": message,
        }
        optional_values = {
            "agent_id": agent_id,
            "agent_type": self._agent_type_for(agent_id) if agent_id else None,
            "order_id": order_id,
            "trade_id": trade_id,
            "side": side,
            "price": round(float(price), 6) if price is not None else None,
            "quantity": int(quantity) if quantity is not None else None,
            "status": status,
        }
        for key, value in optional_values.items():
            if value is not None:
                event[key] = value
        self._event_log.append(event)

    @staticmethod
    def _order_trace_status(order: Order, fallback: str = "submitted") -> str:
        if order.is_filled:
            return "filled"
        if order.filled_quantity > 0:
            return "partial"
        if order.status == OrderStatus.CANCELLED:
            return "cancelled"
        return fallback

    def _record_recent_order(self, order: Order, *, status: Optional[str] = None) -> None:
        trace_status = status or self._order_trace_status(order)
        self._recent_orders.append(
            {
                "id": order.order_id,
                "agent_id": order.agent_id,
                "agent_type": self._agent_type_for(order.agent_id),
                "side": order.side.value.upper(),
                "price": round(float(order.price), 6),
                "quantity": int(order.filled_quantity or order.quantity),
                "status": trace_status,
                "timestamp": round(float(self.current_time), 6),
            }
        )

    def _process_order(self, order: Order) -> None:
        """Exchange receives and processes an order."""
        if order.quantity <= 0:
            logger.warning(f"Rejected non-positive order quantity from {order.agent_id}: {order.quantity}")
            return
        if not math.isfinite(order.price):
            logger.warning(f"Rejected non-finite order price from {order.agent_id}: {order.price}")
            return

        self._submitted_order_count += 1
        self._submitted_notional += abs(order.price * order.quantity)
        self._record_recent_order(order, status="submitted")
        trace_order_events = order.agent_id not in {
            "REFERENCE_FLOW",
            "SCENARIO_FLOW",
            "LIQUIDITY_SHOCK_FLOW",
        }
        if trace_order_events:
            self._record_event(
                "order_submission",
                f"{order.agent_id} submitted {order.side.value.upper()} {order.order_type.value} order",
                agent_id=order.agent_id,
                order_id=order.order_id,
                side=order.side.value.upper(),
                price=order.price,
                quantity=order.quantity,
                status="submitted",
            )
        if order.order_type == OrderType.STOP:
            self._park_stop_order(order)
            return

        if self._session_profile()[0] == "PREOPEN":
            self._accumulate_preopen_order(order)
            return

        reference_mid = self.order_book.mid_price or self.current_price or self.initial_price
        # Stamp with the sim clock so book time-priority and trade times are deterministic.
        order.timestamp = self.current_time
        trades = self.order_book.add_order(order)
        for trade in trades:
            trade.timestamp = self.current_time
        self._all_trades.extend(trades)
        if trades:
            self._matched_order_count += 1

        owner = self.get_agent(order.agent_id)
        if (
            owner is not None
            and order.order_type in RESTING_ORDER_TYPES
            and order.remaining_quantity > 0
        ):
            owner.active_orders[order.order_id] = order
            self.kernel.schedule(
                self.order_ttl_seconds,
                EventType.CANCEL_ARRIVAL,
                self._cancel_order,
                order.order_id,
            )
        for trade in trades:
            self.current_price = trade.price
            self._price_history.append(self.current_price)
            signed_qty = trade.quantity if order.side == OrderSide.BUY else -trade.quantity
            self._recent_volume_history.append((self.current_time, signed_qty))
            if reference_mid and reference_mid > 0:
                self._slippage_bps_samples.append(
                    abs(trade.price - reference_mid) / reference_mid * 10_000
                )
            if trace_order_events:
                self._record_event(
                    "order_match",
                    f"Matched {trade.quantity} @ {trade.price:.2f}",
                    agent_id=order.agent_id,
                    order_id=order.order_id,
                    trade_id=trade.trade_id,
                    side=order.side.value.upper(),
                    price=trade.price,
                    quantity=trade.quantity,
                    status=self._order_trace_status(order),
                )
                self._record_event(
                    "fill",
                    f"{order.agent_id} filled {trade.quantity} @ {trade.price:.2f}",
                    agent_id=order.agent_id,
                    order_id=order.order_id,
                    trade_id=trade.trade_id,
                    side=order.side.value.upper(),
                    price=trade.price,
                    quantity=trade.quantity,
                    status=self._order_trace_status(order),
                )

            buyer = self.get_agent(trade.buyer_agent_id)
            if buyer is not None:
                self.kernel.schedule(
                    self.latency_model.get_latency(buyer.agent_type),
                    EventType.MARKET_DATA,
                    buyer.update_position,
                    trade,
                )
            if trade.seller_agent_id != trade.buyer_agent_id:
                seller = self.get_agent(trade.seller_agent_id)
                if seller is not None:
                    self.kernel.schedule(
                        self.latency_model.get_latency(seller.agent_type),
                        EventType.MARKET_DATA,
                        seller.update_position,
                        trade,
                    )

        if trades:
            self._record_recent_order(order, status=self._order_trace_status(order))
            if order.agent_id == "REFERENCE_FLOW":
                self._record_event(
                    "reference_flow",
                    f"Latent value moved the book {order.side.value.upper()}",
                    agent_id=order.agent_id,
                    order_id=order.order_id,
                    side=order.side.value.upper(),
                    price=trades[-1].price,
                    quantity=sum(trade.quantity for trade in trades),
                    status=self._order_trace_status(order),
                )
        elif order.status == OrderStatus.CANCELLED:
            self._terminal_cancel_count += 1
            self._record_recent_order(order, status="cancelled")
            self._record_event(
                "cancellation",
                f"{order.agent_id} order cancelled with no executable liquidity",
                agent_id=order.agent_id,
                order_id=order.order_id,
                side=order.side.value.upper(),
                price=order.price,
                quantity=order.quantity,
                status="cancelled",
            )

        self._prune_inactive_orders()
        self._trigger_stop_orders()

    def _accumulate_preopen_order(self, order: Order) -> None:
        """Collect a pre-open order. The book may cross; nothing executes yet."""
        if order.order_type == OrderType.MARKET:
            # At-market interest: participates at whatever the auction clears at.
            # Priced far through the book so it always qualifies; the extreme price
            # loses on matched volume, so it cannot set the clearing price itself.
            # Anchored to the session reference (previous close), never the crossed
            # pre-open mid — otherwise each at-market order drags the next one further.
            reference = self.current_price or self.initial_price
            order.order_type = OrderType.LIMIT
            order.price = round(
                reference * (1.2 if order.side == OrderSide.BUY else 0.8), 2
            )

        order.timestamp = self.current_time
        self.order_book.accept_without_matching(order)
        owner = self.get_agent(order.agent_id)
        if owner is not None:
            owner.active_orders[order.order_id] = order

    def _run_opening_auction(self) -> None:
        """Uncross the accumulated pre-open book at a single equilibrium price."""
        clearing_price, trades = self.order_book.uncross_auction()
        if clearing_price is None:
            return

        self.current_price = clearing_price
        self._price_history.append(clearing_price)
        self._all_trades.extend(trades)
        matched = sum(trade.quantity for trade in trades)
        self._record_event(
            "auction_uncross",
            f"Opening auction cleared {matched} shares at {clearing_price:.2f}",
            severity="warning",
            price=clearing_price,
            quantity=matched,
            status="uncrossed",
        )
        for trade in trades:
            trade.timestamp = self.current_time
            for agent_id in (trade.buyer_agent_id, trade.seller_agent_id):
                agent = self.get_agent(agent_id)
                if agent is not None:
                    agent.update_position(trade)
        self._prune_inactive_orders()

    def _park_stop_order(self, order: Order) -> None:
        """Hold a stop at the venue. It is invisible to the book until it triggers."""
        self._resting_stops.append(order)
        self._record_event(
            "stop_placed",
            f"{order.agent_id} placed a {order.side.value.upper()} stop at {order.price:.2f}",
            agent_id=order.agent_id,
            order_id=order.order_id,
            side=order.side.value.upper(),
            price=order.price,
            quantity=order.quantity,
            status="resting",
        )

    def _trigger_stop_orders(self) -> None:
        """Convert stops the last print has breached into market orders.

        Triggered stops are scheduled rather than executed inline, so a cascade
        (stop → print → further stops) unwinds through the event loop instead of
        recursing. This is the mechanism that makes a flash crash self-reinforce.
        """
        if not self._resting_stops:
            return

        price = self.current_price
        still_resting: List[Order] = []
        for stop in self._resting_stops:
            breached = (
                price >= stop.price if stop.side == OrderSide.BUY else price <= stop.price
            )
            owner = self.get_agent(stop.agent_id)
            if not breached or owner is None:
                still_resting.append(stop)
                continue

            # A stop protects a position; it must never open a new one.
            exit_sign = -1 if stop.side == OrderSide.BUY else 1
            quantity = min(stop.quantity, max(0, owner.position * exit_sign))
            if quantity < 1:
                continue  # position already gone — the stop dies with it

            self._record_event(
                "stop_triggered",
                f"{stop.agent_id} stop triggered at {price:.2f}",
                severity="warning",
                agent_id=stop.agent_id,
                order_id=stop.order_id,
                side=stop.side.value.upper(),
                price=price,
                quantity=quantity,
                status="triggered",
            )
            self.kernel.schedule(
                STOP_TRIGGER_LATENCY_SECONDS,
                EventType.ORDER_ARRIVAL,
                self._process_order,
                Order(
                    agent_id=stop.agent_id,
                    side=stop.side,
                    order_type=OrderType.MARKET,
                    price=price,
                    quantity=quantity,
                ),
            )
        self._resting_stops = still_resting

    def _cancel_order(self, order_id: str, *, record_event: bool = True) -> bool:
        """Cancel a resting order and clear its agent-side tracking."""
        self._cancel_request_count += 1
        cancelled = self.order_book.cancel_order(order_id)
        for agent in self.agents:
            agent.active_orders.pop(order_id, None)
        if cancelled:
            self._accepted_cancel_count += 1
            if record_event:
                self._record_event(
                    "cancellation",
                    f"Cancelled stale order {order_id}",
                    order_id=order_id,
                    status="cancelled",
                )
            logger.debug(f"Cancelled stale order {order_id}")
        return cancelled

    def _prune_inactive_orders(self) -> None:
        """Remove filled or cancelled resting orders from agent-side tracking."""
        for agent in self.agents:
            inactive_ids = [
                order_id
                for order_id, order in agent.active_orders.items()
                if order.is_filled
                or order.status == OrderStatus.CANCELLED
                or order.remaining_quantity <= 0
            ]
            for order_id in inactive_ids:
                agent.active_orders.pop(order_id, None)

    def _request_agent_orders(
        self, agent: BaseAgent, observed_state: Optional[Dict] = None
    ) -> None:
        """Process an agent action cycle through the simulator's normal order path.

        `observed_state` is the market-data snapshot that actually reached the agent;
        it is already `latency` seconds stale by the time the agent acts on it.
        """
        note_cancel_result = getattr(agent, "note_cancel_result", None)
        state = (
            self.get_market_state(
                include_oracle=(
                    self.informed_oracle_access
                    and agent.agent_type == "Informed"
                )
            )
            if observed_state is None
            else observed_state
        )
        for order_id in agent.cancel_for_state(state):
            cancelled = self._cancel_order(order_id)
            if callable(note_cancel_result):
                note_cancel_result(cancelled)

        orders = agent.decide_action(state)
        was_halted = agent.risk_halted
        orders, rejected = enforce_trading_rules(agent, orders, state)
        if agent.risk_halted and not was_halted:
            self._record_event(
                "risk_halt",
                f"{agent.agent_id} hit max drawdown — reduce-only until session reset",
                severity="warning",
                agent_id=agent.agent_id,
                status="halted",
            )
        for order, reason in rejected:
            if reason == "risk_halted":
                continue  # halt already announced once; skip per-wakeup spam
            self._record_event(
                "risk_block",
                f"{agent.agent_id} order blocked by {reason}",
                severity="warning",
                agent_id=agent.agent_id,
                order_id=order.order_id,
                side=order.side.value.upper(),
                price=order.price,
                quantity=order.quantity,
                status="rejected",
            )
        for order in orders:
            self.kernel.schedule(
                self.latency_model.get_latency(agent.agent_type),
                EventType.ORDER_ARRIVAL,
                self._process_order,
                order,
            )

    def _agent_wakeup(self, agent: BaseAgent) -> None:
        """Publish market data to an agent; it decides once that data reaches it."""
        if not self.running:
            return

        # Inbound leg: the book as it looks now reaches the agent one latency hop
        # later, so it always decides on a stale view. The outbound leg is applied
        # again in _request_agent_orders, making the round trip 2x latency.
        self.kernel.schedule(
            self.latency_model.get_latency(agent.agent_type),
            EventType.MARKET_DATA,
            self._deliver_market_data,
            (
                agent,
                self.get_market_state(
                    include_oracle=(
                        self.informed_oracle_access
                        and agent.agent_type == "Informed"
                    )
                ),
            ),
        )

        interval = getattr(agent, "wakeup_interval", 1.0)
        jitter = self.rng.uniform(0.9, 1.1)
        _, activity_multiplier = self._session_profile()
        self.kernel.schedule(
            interval * jitter / activity_multiplier,
            EventType.WAKEUP,
            self._agent_wakeup,
            agent,
        )

    def _square_off_open_positions(self) -> None:
        """Force intraday books flat near the close, as a broker auto-square-off would.

        Bypasses the rule gate on purpose: square-off is the venue acting on the
        agent, not the agent choosing to trade.
        """
        for agent in self.agents:
            if agent.position == 0:
                continue
            side = OrderSide.SELL if agent.position > 0 else OrderSide.BUY
            for order_id in agent.cancel_all_active_orders():
                self._cancel_order(order_id)
            order = Order(
                agent_id=agent.agent_id,
                side=side,
                order_type=OrderType.MARKET,
                price=self.order_book.mid_price or self.current_price,
                quantity=abs(agent.position),
            )
            self._record_event(
                "square_off",
                f"{agent.agent_id} auto-squared-off {abs(agent.position)} shares at the close",
                severity="warning",
                agent_id=agent.agent_id,
                order_id=order.order_id,
                side=side.value.upper(),
                quantity=order.quantity,
                status="squared_off",
            )
            self.kernel.schedule(
                self.latency_model.get_latency(agent.agent_type),
                EventType.ORDER_ARRIVAL,
                self._process_order,
                order,
            )

    def _settle_close_positions(self) -> None:
        """Fill any residual intraday position against closing-auction liquidity."""
        price = self.order_book.mid_price or self.current_price
        for agent in self.agents:
            for order_id in agent.cancel_all_active_orders():
                self._cancel_order(order_id)
            if agent.position == 0:
                continue
            quantity = abs(agent.position)
            order = Order(
                agent_id=agent.agent_id,
                side=OrderSide.SELL if agent.position > 0 else OrderSide.BUY,
                order_type=OrderType.MARKET,
                price=price,
                quantity=quantity,
            )
            if order.side == OrderSide.BUY:
                trade = Trade(
                    order.order_id,
                    "CLOSE_AUCTION",
                    agent.agent_id,
                    "CLOSE_AUCTION",
                    price,
                    quantity,
                    taker_agent_id=agent.agent_id,
                    timestamp=self.current_time,
                )
            else:
                trade = Trade(
                    "CLOSE_AUCTION",
                    order.order_id,
                    "CLOSE_AUCTION",
                    agent.agent_id,
                    price,
                    quantity,
                    taker_agent_id=agent.agent_id,
                    timestamp=self.current_time,
                )
            agent.update_position(trade)
            self._all_trades.append(trade)
            self._submitted_order_count += 1
            self._matched_order_count += 1
            self._record_event(
                "close_settlement",
                f"{agent.agent_id} closed {quantity} residual shares at {price:.2f}",
                severity="warning",
                agent_id=agent.agent_id,
                order_id=order.order_id,
                side=order.side.value.upper(),
                price=price,
                quantity=quantity,
                status="filled",
            )
        self._resting_stops.clear()
        self._prune_inactive_orders()

    def _deliver_market_data(self, payload: tuple) -> None:
        """Hand a delayed snapshot to its agent and let it act on that stale view."""
        agent, snapshot = payload
        if not self.running:
            return
        try:
            self._request_agent_orders(agent, observed_state=snapshot)
        except Exception as exc:
            logger.error(f"Agent {agent.agent_id} error: {exc}")

    def _session_profile(self) -> tuple[str, float]:
        """Return the SIM session phase and relative agent activity."""
        if self.duration_seconds <= 0:
            return "CONTINUOUS", 1.0

        progress = self.current_time / self.duration_seconds
        if progress < 0.04 and self.scenario.enable_opening_auction:
            return "PREOPEN", 1.2  # order accumulation; nothing trades until uncrossing
        if progress < 0.1:
            return "OPEN", 1.5
        if progress >= 0.97:
            return "SQUAREOFF", 1.6  # broker auto-square-off window for intraday books
        if progress >= 0.9:
            return "CLOSE", 1.35
        return "CONTINUOUS", 0.85

    def run(self, steps: Optional[int] = None) -> Dict:
        """Run the simulation synchronously until the requested horizon."""
        self.reset()
        self.running = True
        target_time = float(steps if steps is not None else self.duration_seconds)

        logger.info(f"Starting kernel event loop until T={target_time:.2f}s")
        while self.running and self.current_time < target_time:
            self.step()

        self.running = False
        return self.get_results()

    def step(self) -> Dict:
        """Advance the simulation by one second of simulated time."""
        if not self.running:
            self.running = True

        for agent in self.agents:
            if getattr(agent, "external_action_controlled", False):
                try:
                    self._request_agent_orders(agent)
                except Exception as exc:
                    logger.error(f"Externally controlled agent {agent.agent_id} error: {exc}")

        self.step_count += 1
        target_time = self.current_time + 1.0
        if self._session_profile()[0] == "SQUAREOFF":
            self._square_off_open_positions()
        self.kernel.run_until(target_time)

        phase = self._session_profile()[0]
        if self._last_session_phase == "PREOPEN" and phase != "PREOPEN":
            self._run_opening_auction()
        self._last_session_phase = phase

        # Advance oracle
        if self.oracle.enabled:
            self.oracle.advance(dt=1.0)

        self._apply_reference_flow()
        self._apply_scenario_driver()
        self._ensure_liquidity_floor()

        if (
            self.order_book.mid_price is not None
            and self._session_profile()[0] != "PREOPEN"  # crossed book has no meaningful mid
        ):
            self.current_price = self.order_book.mid_price

        self._price_history.append(self.current_price)

        if self.current_time >= self.duration_seconds:
            self._settle_close_positions()

        state = self.get_market_state()

        self._state_history.append(state)
        return state

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Return the simulator agent with the requested ID, if present."""
        return self._agents_by_id.get(agent_id)

    def get_market_state(self, include_oracle: Optional[bool] = None) -> Dict:
        """Return the current market state snapshot."""
        depth_data = self.order_book.get_depth(levels=10)
        volatility = self._compute_volatility()
        session_phase, activity_multiplier = self._session_profile()

        recent_price_change = 0.0
        if len(self._price_history) >= 5 and self._price_history[-5] > 0:
            recent_price_change = (
                self._price_history[-1] - self._price_history[-5]
            ) / self._price_history[-5]

        volume_window = 10.0
        recent_signed_volume = sum(
            qty for ts, qty in self._recent_volume_history if (self.current_time - ts) <= volume_window
        )

        bid_sum = sum(level["size"] for level in depth_data["bids"])
        ask_sum = sum(level["size"] for level in depth_data["asks"])
        total_depth = bid_sum + ask_sum
        imbalance = (bid_sum - ask_sum) / max(1, bid_sum + ask_sum)
        trade_rate_per_second = len(self._all_trades) / max(1.0, self.current_time)

        # A pre-open book is deliberately crossed, so its mid/spread are meaningless.
        # Publish the session reference as the indicative price, as venues do.
        preopen = session_phase == "PREOPEN"
        mid_price = self.current_price if preopen else (self.order_book.mid_price or self.current_price)

        scenario_phase, recovery_progress = self._liquidity_shock_state()
        scenario_state: Dict[str, Any] = {
            "name": self.scenario.name,
            "label": self.scenario.label,
            "description": self.scenario.description,
            "phase": scenario_phase,
        }
        if self.scenario.name == "liquidity_shock":
            baseline_depth = max(1, self._liquidity_shock_baseline_depth)
            baseline_spread = max(0.01, self._liquidity_shock_baseline_spread)
            scenario_state["liquidity"] = {
                "baseline_depth": self._liquidity_shock_baseline_depth,
                "depth_depletion": round(max(0.0, 1.0 - total_depth / baseline_depth), 4),
                "spread_ratio": round((self.order_book.spread or 0.0) / baseline_spread, 4),
                "recovery_progress": round(recovery_progress, 4),
            }

        state = {
            "venue": self.venue,
            "market": self.venue,
            "current_time": self.current_time,
            "mid_price": mid_price,
            "best_bid": None if preopen else self.order_book.best_bid,
            "best_ask": None if preopen else self.order_book.best_ask,
            "spread": 0.0 if preopen else (self.order_book.spread or 0.0),
            "bid_depth": bid_sum,
            "ask_depth": ask_sum,
            "bid_levels": depth_data["bids"],
            "ask_levels": depth_data["asks"],
            "order_book_imbalance": imbalance,
            "recent_signed_volume": recent_signed_volume,
            "recent_price_change": recent_price_change,
            "trade_rate_per_second": trade_rate_per_second,
            "total_depth": total_depth,
            "current_price": self.current_price,
            "time_to_close": max(0.0, self.duration_seconds - self.current_time),
            "session_phase": session_phase,
            "activity_multiplier": activity_multiplier,
            "volatility": volatility,
            "scenario": scenario_state,
            "agents": {
                agent.agent_id: {
                    "type": agent.agent_type,
                    "position": agent.position,
                    "inventory_ratio": self._inventory_ratio(agent),
                }
                for agent in self.agents
            },
            "step": self.step_count,
        }
        expose_oracle = (
            self.informed_oracle_access
            if include_oracle is None
            else bool(include_oracle)
        )
        if self.oracle.enabled and expose_oracle:
            state["oracle"] = self.oracle.get_mispricing(self.current_price)
        return state

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

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent exchange events newest first."""
        limit = max(0, limit)
        if limit == 0:
            return []
        return list(reversed(self._event_log))[:limit]

    def get_recent_orders(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent order status snapshots newest first."""
        limit = max(0, limit)
        if limit == 0:
            return []
        return list(reversed(self._recent_orders))[:limit]

    def get_order_flow_summary(self, window_seconds: float = 10.0) -> Dict[str, Any]:
        """Summarize recent aggressor flow and run-level execution counters."""
        buy_volume = 0
        sell_volume = 0
        for timestamp, signed_qty in self._recent_volume_history:
            if (self.current_time - timestamp) > window_seconds:
                continue
            if signed_qty >= 0:
                buy_volume += int(signed_qty)
            else:
                sell_volume += abs(int(signed_qty))

        fills = len(self._all_trades)
        cancelled = self._accepted_cancel_count + self._terminal_cancel_count
        match_rate = (
            self._matched_order_count / self._submitted_order_count
        ) * 100 if self._submitted_order_count else 0.0
        return {
            "submitted": self._submitted_order_count,
            "fills": fills,
            "cancelled": cancelled,
            "match_rate": round(match_rate, 2),
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "submitted_notional": round(self._submitted_notional, 4),
        }

    def get_export_snapshot(self, warning_timeline: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Return a serializable research snapshot for validation and demos."""
        price_path = [
            {
                "timestamp": state.get("current_time", 0.0),
                "price": state.get("current_price", 0.0),
                "spread": state.get("spread", 0.0),
                "depth": state.get("total_depth", 0),
                "imbalance": state.get("order_book_imbalance", 0.0),
                "signed_volume": state.get("recent_signed_volume", 0.0),
                "volatility": state.get("volatility", 0.0),
            }
            for state in self._state_history
        ]
        timeline = list(warning_timeline or [])

        return {
            "run_config": {
                "scenario": self.scenario.name,
                "seed": self.seed,
                "initial_price": self.initial_price,
                "duration_seconds": self.duration_seconds,
                "speed": self.speed_multiplier,
                "depth_profile": self.depth_profile,
            },
            "price_path": price_path,
            "order_flow": {
                "submitted_orders": self._submitted_order_count,
                "cancel_requests": self._cancel_request_count,
                "accepted_cancels": self._accepted_cancel_count,
                "terminal_cancels": self._terminal_cancel_count,
                "summary": self.get_order_flow_summary(window_seconds=self.duration_seconds),
                "trades": [
                    {
                        "price": trade.price,
                        "quantity": trade.quantity,
                        "buyer_agent_id": trade.buyer_agent_id,
                        "seller_agent_id": trade.seller_agent_id,
                    }
                    for trade in self._all_trades
                ],
            },
            "events": self.get_recent_events(limit=500),
            "recent_orders": self.get_recent_orders(limit=200),
            "agent_metrics": {
                agent.agent_id: agent.get_metrics(self.current_price)
                for agent in self.agents
            },
            "warning_timeline": timeline,
            "validation_metrics": self.get_microstructure_metrics(),
        }

    def get_microstructure_metrics(self) -> Dict[str, float]:
        states = self._state_history or [self.get_market_state()]

        def avg(key: str) -> float:
            values = [float(state.get(key, 0.0) or 0.0) for state in states]
            return round(sum(values) / max(1, len(values)), 6)

        spread_values = [float(state.get("spread", 0.0) or 0.0) for state in states]
        impact_samples = []
        prices = [float(state.get("current_price", 0.0) or 0.0) for state in states]
        for before, after in zip(prices, prices[1:]):
            if before > 0:
                impact_samples.append(abs(after - before) / before * 10_000)

        return {
            "spread_mean": avg("spread"),
            "spread_max": round(max(spread_values) if spread_values else 0.0, 6),
            "trade_rate_per_second_mean": avg("trade_rate_per_second"),
            "cancel_to_trade_ratio": round(
                self._cancel_request_count / max(1, len(self._all_trades)),
                6,
            ),
            "depth_imbalance_mean": avg("order_book_imbalance"),
            "signed_volume_abs_mean": round(
                sum(abs(float(state.get("recent_signed_volume", 0.0) or 0.0)) for state in states)
                / max(1, len(states)),
                6,
            ),
            "volatility_mean": avg("volatility"),
            "impact_bps_mean": round(
                sum(impact_samples) / max(1, len(impact_samples)),
                6,
            ),
            "slippage_bps_mean": round(
                sum(self._slippage_bps_samples) / max(1, len(self._slippage_bps_samples)),
                6,
            ),
        }

    def _compute_volatility(self) -> float:
        """Compute annualized volatility from recent log returns."""
        if len(self._price_history) < 20:
            return 0.0

        window_size = 20
        window = [
            self._price_history[-window_size + i]
            for i in range(window_size)
        ]
        log_returns = []
        for i in range(1, len(window)):
            if window[i] > 0 and window[i - 1] > 0:
                log_returns.append(math.log(window[i] / window[i - 1]))

        if len(log_returns) < 2:
            return 0.0

        mean_ret = sum(log_returns) / len(log_returns)
        variance = sum((ret - mean_ret) ** 2 for ret in log_returns) / (len(log_returns) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0

        return std * math.sqrt(252 * 390) * self.scenario.volatility_multiplier

    def _inventory_ratio(self, agent: BaseAgent) -> float:
        limit = (
            getattr(agent, "max_inventory", None)
            or getattr(agent, "max_position", None)
            or getattr(agent, "position_limit", None)
        )
        if not limit:
            return 0.0
        return abs(agent.position) / float(limit)

    def stop(self) -> None:
        """Stop the simulation loop."""
        self.running = False
        logger.info("Simulation stopped")


# ── Sandbox Presets ─────────────────────────────────────────────────────────

def get_sandbox_presets() -> Dict:
    """Return available sandbox configuration presets."""
    return {
        "minimal": {
            "name": "Minimal", "description": "10 agents — fast iteration", "icon": "⚡",
            "agents": {"MarketMaker": 1, "HFT": 2, "Noise": 3, "Retail": 2, "Informed": 1, "Sentiment": 1},
            "oracle": False, "latency": "deterministic",
        },
        "balanced": {
            "name": "Balanced", "description": "40 agents — realistic mix", "icon": "⚖️",
            "agents": {"MarketMaker": 3, "HFT": 2, "Institutional": 2, "Retail": 10, "Informed": 3,
                       "Noise": 10, "Momentum": 2, "MeanReversion": 2, "Spoofing": 0, "Sentiment": 5,
                       "LiquidityTrader": 1},
            "oracle": False, "latency": "deterministic",
        },
        "institutional": {
            "name": "Institutional", "description": "80 agents — deep market", "icon": "🏦",
            "agents": {"MarketMaker": 5, "HFT": 4, "Institutional": 8, "Retail": 15, "Informed": 5,
                       "Noise": 20, "Momentum": 8, "MeanReversion": 5, "Spoofing": 0, "Sentiment": 8,
                       "LiquidityTrader": 5},
            "oracle": True, "latency": "cubic",
        },
        "stress_test": {
            "name": "Stress Test", "description": "200 agents — chaos mode", "icon": "🔥",
            "agents": {"MarketMaker": 8, "HFT": 10, "Institutional": 5, "Retail": 30, "Informed": 10,
                       "Noise": 100, "Momentum": 12, "MeanReversion": 10, "Spoofing": 0, "Sentiment": 12,
                       "LiquidityTrader": 3},
            "oracle": True, "latency": "cubic",
        },
    }


def create_sandbox_agents(
    preset: str = "balanced",
    custom_agents: Optional[Dict] = None,
    scenario: str | ScenarioConfig = "normal",
    seed: Optional[int] = None,
) -> List:
    """Create agents from a preset name or custom dict."""
    from ..agents.market_maker import MarketMakerAgent
    from ..agents.hft_agent import HFTAgent
    from ..agents.institutional import InstitutionalAgent
    from ..agents.retail import RetailAgent
    from ..agents.informed import InformedAgent
    from ..agents.noise import NoiseAgent
    from ..agents.momentum import MomentumAgent
    from ..agents.mean_reversion import MeanReversionAgent
    from ..agents.spoofing import SpoofingAgent
    from ..agents.sentiment import SentimentAgent
    from ..agents.liquidity_trader import LiquidityTraderAgent

    AGENT_MAP = {
        "MarketMaker": MarketMakerAgent, "HFT": HFTAgent, "Institutional": InstitutionalAgent,
        "Retail": RetailAgent, "Informed": InformedAgent, "Noise": NoiseAgent,
        "Momentum": MomentumAgent, "MeanReversion": MeanReversionAgent,
        "Spoofing": SpoofingAgent, "Sentiment": SentimentAgent, "LiquidityTrader": LiquidityTraderAgent,
    }

    if custom_agents and any(v > 0 for v in custom_agents.values()):
        agent_counts = dict(custom_agents)
    else:
        presets = get_sandbox_presets()
        cfg = presets.get(preset, presets["balanced"])
        agent_counts = dict(cfg["agents"])
    agent_counts = apply_scenario_agent_counts(agent_counts, scenario)

    rng = random.Random(seed)
    agents = []
    for agent_type, count in agent_counts.items():
        cls = AGENT_MAP.get(agent_type)
        if cls and count > 0:
            for i in range(int(count)):
                agent = cls(f"{agent_type}_{i}")
                agent.set_random_seed(rng.getrandbits(64))
                agent.reset()

                agent.latency_seconds = max(
                    0.000001,
                    agent.latency_seconds * rng.uniform(0.85, 1.15),
                )
                if hasattr(agent, "wakeup_interval"):
                    agent.wakeup_interval = max(
                        0.01,
                        agent.wakeup_interval * rng.uniform(0.85, 1.15),
                    )

                profile = agent.risk_profile
                base_order_size = max(
                    profile.min_order_size,
                    round(profile.base_order_size * rng.uniform(0.8, 1.2)),
                )
                max_inventory = max(
                    base_order_size,
                    round(profile.max_inventory * rng.uniform(0.85, 1.15)),
                )
                agent.risk_profile = replace(
                    profile,
                    base_order_size=base_order_size,
                    max_inventory=max_inventory,
                )
                agents.append(agent)
    return agents
