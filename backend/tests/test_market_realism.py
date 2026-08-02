import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.agents.base_agent import (
    BROKERAGE_CAP,
    BROKERAGE_PCT,
    EXCHANGE_TXN_PCT,
    SEBI_TURNOVER_PCT,
    STAMP_DUTY_BUY_PCT,
    STT_SELL_PCT,
    BaseAgent,
)
from backend.src.agents.noise import NoiseAgent
from backend.src.market.latency_model import LatencyConfig, LatencyMode
from backend.src.market.order import Order, OrderSide, OrderStatus, OrderType
from backend.src.market.order_book import OrderBook
from backend.src.market.simulator import MarketSimulator


def _order(agent_id, side, order_type=OrderType.LIMIT, price=100.0, quantity=100):
    return Order(agent_id, side, order_type, price, quantity)


def test_self_trade_is_prevented_and_resting_order_cancelled():
    book = OrderBook()
    own_ask = _order("mm", OrderSide.SELL, price=100.0)
    other_ask = _order("other", OrderSide.SELL, price=100.0)
    book.add_order(own_ask)
    book.add_order(other_ask)

    trades = book.add_order(_order("mm", OrderSide.BUY, price=100.0, quantity=100))

    assert own_ask.status == OrderStatus.CANCELLED
    assert [t.seller_agent_id for t in trades] == ["other"]  # swept past its own quote


def test_seed_liquidity_is_exempt_from_stp():
    book = OrderBook()
    book.add_order(_order("SEED", OrderSide.SELL, price=100.0))

    trades = book.add_order(_order("SEED", OrderSide.BUY, price=100.0))

    assert len(trades) == 1  # bootstrap liquidity is not a real participant


def test_market_order_stops_at_the_protection_band():
    book = OrderBook()
    for price in (100.0, 101.0, 105.0):  # 105 is >2% above the 100 touch
        book.add_order(_order("mm", OrderSide.SELL, price=price, quantity=10))

    order = _order("taker", OrderSide.BUY, OrderType.MARKET, price=0.0, quantity=30)
    trades = book.add_order(order)

    assert [t.price for t in trades] == [100.0, 101.0]
    assert order.status == OrderStatus.CANCELLED  # remainder unfilled, not printed at 105
    assert book.best_ask == 105.0


def test_market_order_rejects_stale_touch_outside_arrival_reference_band():
    book = OrderBook()
    book.add_order(_order("maker", OrderSide.SELL, price=101.0, quantity=10))
    order = _order("taker", OrderSide.BUY, OrderType.MARKET, price=100.0, quantity=10)

    trades = book.add_order(order)

    assert trades == []
    assert order.status == OrderStatus.CANCELLED
    assert book.best_ask == 101.0


def test_liquidity_floor_repairs_a_deep_but_excessively_wide_book():
    sim = MarketSimulator([], initial_price=100.0, seed=3)
    sim.order_book.replace_depth(
        bids=[{"price": 99.0, "size": 5_000}],
        asks=[{"price": 101.0, "size": 5_000}],
    )

    sim._ensure_liquidity_floor()

    assert sim.order_book.spread <= 0.04


def test_liquidity_floor_rebuilds_around_the_latest_executed_price():
    sim = MarketSimulator([], initial_price=100.0, seed=3)
    sim.current_price = 100.20
    sim.order_book.replace_depth(
        bids=[{"price": 99.0, "size": 5_000}],
        asks=[{"price": 101.0, "size": 5_000}],
    )

    sim._ensure_liquidity_floor()

    assert sim.order_book.mid_price == pytest.approx(100.20)
    assert sim.order_book.spread == pytest.approx(0.02)


class LagRecordingAgent(BaseAgent):
    """Records how stale the market data was each time it was asked to decide."""

    def __init__(self, agent_id, agent_type):
        super().__init__(agent_id, agent_type)
        self.simulator = None
        self.lags = []

    def decide_action(self, market_state):
        self.lags.append(self.simulator.current_time - market_state["current_time"])
        return []


def _run_with_lag_recorders(latency_mode, steps=5):
    agents = [LagRecordingAgent("hft", "HFT"), LagRecordingAgent("retail", "Retail")]
    sim = MarketSimulator(agents, latency_config=LatencyConfig(mode=latency_mode), seed=5)
    for agent in agents:
        agent.simulator = sim
    sim.running = True
    for _ in range(steps):
        sim.step()
    return {agent.agent_id: agent.lags for agent in agents}


def test_agents_decide_on_market_data_stale_by_their_own_latency():
    lags = _run_with_lag_recorders(LatencyMode.DETERMINISTIC)

    assert lags["hft"] and lags["retail"]
    assert all(lag == pytest.approx(0.000_001) for lag in lags["hft"])  # co-located tier
    assert all(lag == pytest.approx(0.010) for lag in lags["retail"])  # consumer ISP tier
    assert max(lags["hft"]) < min(lags["retail"])  # co-location is a real edge


def test_zero_latency_mode_still_delivers_fresh_data():
    lags = _run_with_lag_recorders(LatencyMode.ZERO)

    assert lags["retail"]
    assert all(lag == 0.0 for lag in lags["retail"])


def _queued_order_arrivals(sim):
    from backend.src.market.kernel import EventType

    return sum(1 for e in sim.kernel.queue if e.event_type == EventType.ORDER_ARRIVAL)


def _stop_sim():
    """A one-agent sim holding a long position, with deep bids to sell into."""
    agent = NoiseAgent("holder", initial_capital=1_000_000.0)
    sim = MarketSimulator([agent], seed=3)
    agent.position = 500
    agent.avg_entry_price = 100.0
    return sim, agent


def test_stop_is_invisible_until_price_breaches_it():
    sim, agent = _stop_sim()
    stop = Order("holder", OrderSide.SELL, OrderType.STOP, 95.0, 500)

    sim._process_order(stop)

    assert sim._resting_stops == [stop]
    assert sim.order_book.get_total_depth(levels=10) > 0
    assert all(o.order_id != stop.order_id for o in sim.order_book.bids)  # not on the book

    sim.current_price = 96.0  # above the trigger
    sim._trigger_stop_orders()
    assert sim._resting_stops == [stop]  # still parked

    sim.current_price = 94.5  # breached
    sim._trigger_stop_orders()
    assert sim._resting_stops == []
    assert _queued_order_arrivals(sim) == 1  # converted to a market order


def test_triggered_stop_cannot_open_a_new_position():
    sim, agent = _stop_sim()
    sim._process_order(Order("holder", OrderSide.SELL, OrderType.STOP, 95.0, 500))
    agent.position = 0  # squared off before the stop ever fired

    sim.current_price = 90.0
    sim._trigger_stop_orders()

    assert sim._resting_stops == []
    assert _queued_order_arrivals(sim) == 0  # the stop died with the position


def test_post_only_is_rejected_rather_than_crossing():
    book = OrderBook()
    book.add_order(_order("mm", OrderSide.SELL, price=100.0))

    crossing = _order("taker", OrderSide.BUY, OrderType.POST_ONLY, price=100.5)
    resting = _order("taker", OrderSide.BUY, OrderType.POST_ONLY, price=99.5)

    assert book.add_order(crossing) == []
    assert crossing.status == OrderStatus.CANCELLED
    assert book.add_order(resting) == []
    assert book.best_bid == 99.5  # posted, not crossed


def test_ioc_fills_what_it_can_and_never_rests():
    book = OrderBook()
    book.add_order(_order("mm", OrderSide.SELL, price=100.0, quantity=40))

    ioc = _order("taker", OrderSide.BUY, OrderType.IOC, price=100.0, quantity=100)
    trades = book.add_order(ioc)

    assert sum(t.quantity for t in trades) == 40
    assert ioc.status == OrderStatus.CANCELLED
    assert book.best_bid is None  # remainder did not post


def test_iceberg_hides_reserve_from_market_data_but_still_fills():
    book = OrderBook()
    iceberg = _order("inst", OrderSide.SELL, price=100.0, quantity=1_000)
    iceberg.display_quantity = 100
    book.add_order(iceberg)

    assert book.get_depth(levels=5)["asks"] == [{"price": 100.0, "size": 100}]
    assert book.get_total_depth(levels=5) == 100  # 900 shares are invisible

    trades = book.add_order(_order("taker", OrderSide.BUY, OrderType.MARKET, quantity=500))

    assert sum(t.quantity for t in trades) == 500  # hidden size is real liquidity
    assert book.get_depth(levels=5)["asks"] == [{"price": 100.0, "size": 100}]


def test_auction_clears_at_the_max_volume_price():
    book = OrderBook()
    # Demand at 101 (60) and 100 (40); supply at 99 (50) and 100 (30).
    for price, qty in ((101.0, 60), (100.0, 40)):
        book.accept_without_matching(_order("b", OrderSide.BUY, price=price, quantity=qty))
    for price, qty in ((99.0, 50), (100.0, 30)):
        book.accept_without_matching(_order("s", OrderSide.SELL, price=price, quantity=qty))

    price, trades = book.uncross_auction()

    # At 100: demand 100, supply 80 → 80 matched. At 101: demand 60, supply 80 → 60.
    assert price == 100.0
    assert sum(t.quantity for t in trades) == 80
    assert {t.price for t in trades} == {100.0}  # single uniform clearing price


def test_uncrossed_book_has_no_auction_trades():
    book = OrderBook()
    book.accept_without_matching(_order("b", OrderSide.BUY, price=99.0))
    book.accept_without_matching(_order("s", OrderSide.SELL, price=101.0))

    assert book.uncross_auction() == (None, [])


def test_opening_auction_scenario_defers_all_trading_to_the_uncross():
    from backend.src.market.simulator import create_sandbox_agents

    agents = create_sandbox_agents("balanced", seed=8)
    sim = MarketSimulator(agents, scenario="market_open", seed=8, duration_seconds=100)
    sim.running = True

    sim.step()
    assert sim._session_profile()[0] == "PREOPEN"
    assert sim._all_trades == []  # nothing executes during accumulation

    for _ in range(5):
        sim.step()
    assert sim._session_profile()[0] == "OPEN"
    assert any(e["type"] == "auction_uncross" for e in sim._event_log)
    assert sim._all_trades  # price discovery happened at the uncross


def test_session_squares_off_every_book_by_the_close():
    from backend.src.market.simulator import create_sandbox_agents

    agents = create_sandbox_agents("balanced", seed=42)
    sim = MarketSimulator(agents, scenario="normal", seed=42, duration_seconds=120)
    sim.running = True
    phases = set()
    for _ in range(120):
        sim.step()
        phases.add(sim._session_profile()[0])

    assert {"OPEN", "CONTINUOUS", "CLOSE", "SQUAREOFF"} <= phases
    assert all(agent.position == 0 for agent in sim.agents)  # nothing carried overnight
    # With flat books, PnL is fully realized and comparable across agents.
    assert sum(a.get_unrealized_pnl(sim.current_price) for a in sim.agents) == 0.0


def test_squareoff_phase_blocks_new_risk_but_allows_exits():
    from backend.src.agents.risk import enforce_trading_rules

    state = {"mid_price": 100.0, "session_phase": "SQUAREOFF"}
    agent = NoiseAgent("noise", initial_capital=20_000.0)
    agent.position = 100
    agent.avg_entry_price = 100.0

    opening = _order("noise", OrderSide.BUY, OrderType.MARKET, quantity=50)
    exiting = _order("noise", OrderSide.SELL, OrderType.MARKET, quantity=50)
    accepted, rejected = enforce_trading_rules(agent, [opening, exiting], state)

    assert accepted == [exiting]
    assert rejected == [(opening, "squareoff")]


def test_both_sides_pay_and_the_sell_leg_carries_stt():
    book = OrderBook()
    buyer = NoiseAgent("buyer", initial_capital=100_000.0)
    seller = NoiseAgent("seller", initial_capital=100_000.0)
    book.add_order(_order("seller", OrderSide.SELL, price=100.0, quantity=100))

    trade = book.add_order(_order("buyer", OrderSide.BUY, OrderType.MARKET, quantity=100))[0]
    assert trade.taker_agent_id == "buyer"

    buyer.update_position(trade)
    seller.update_position(trade)

    notional = 100 * 100.0  # 10,000
    brokerage = min(notional * BROKERAGE_PCT, BROKERAGE_CAP)
    taxable = brokerage + notional * (EXCHANGE_TXN_PCT + SEBI_TURNOVER_PCT)
    assert buyer.fees_paid == pytest.approx(taxable * 1.18 + notional * STAMP_DUTY_BUY_PCT)
    assert seller.fees_paid == pytest.approx(taxable * 1.18 + notional * STT_SELL_PCT)
    # No rebate on this venue: providing liquidity still costs, and STT makes selling dearer.
    assert seller.fees_paid > buyer.fees_paid > 0


def test_brokerage_accumulates_across_fills_but_is_capped_per_order():
    book = OrderBook()
    taker = NoiseAgent("taker", initial_capital=100_000.0)
    for price in (100.0, 100.5, 101.0):
        book.add_order(_order("mm", OrderSide.SELL, price=price, quantity=10))

    trades = book.add_order(
        _order("taker", OrderSide.BUY, OrderType.MARKET, price=0.0, quantity=30)
    )
    assert len(trades) == 3
    for trade in trades:
        taker.update_position(trade)

    notional = sum(t.value for t in trades)
    brokerage = min(notional * BROKERAGE_PCT, BROKERAGE_CAP)
    taxable = brokerage + notional * (EXCHANGE_TXN_PCT + SEBI_TURNOVER_PCT)
    assert taker.fees_paid == pytest.approx(taxable * 1.18 + notional * STAMP_DUTY_BUY_PCT)
