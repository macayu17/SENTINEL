"""Regression checks for engine bugs fixed during the simulation cleanup."""

import asyncio

from backend.src.agents.momentum import MomentumAgent
from backend.src.agents.spoofing import SpoofingAgent
from backend.src.api import main as api_main
from backend.src.market.order import Order, OrderSide, OrderType
from backend.src.market.order_book import OrderBook
from backend.src.market.simulator import MarketSimulator, create_sandbox_agents


def _state(price, **overrides):
    return {
        "mid_price": price,
        "current_price": price,
        "spread": 0.02,
        "bid_depth": 5_000,
        "ask_depth": 5_000,
        "volatility": 0.001,
        **overrides,
    }


def test_order_ids_never_collide_in_a_long_session():
    # 8-hex-char uuid prefixes collide with ~50% odds by ~77k orders.
    ids = {Order("A", OrderSide.BUY, OrderType.LIMIT, 100.0, 1).order_id for _ in range(200_000)}
    assert len(ids) == 200_000


def test_book_keeps_time_priority_within_a_price_level():
    book = OrderBook()
    first = Order("A", OrderSide.SELL, OrderType.LIMIT, 100.0, 10)
    second = Order("B", OrderSide.SELL, OrderType.LIMIT, 100.0, 10)
    book.add_order(first)
    book.add_order(Order("C", OrderSide.SELL, OrderType.LIMIT, 100.5, 10))
    book.add_order(second)

    trades = book.add_order(Order("T", OrderSide.BUY, OrderType.LIMIT, 100.0, 15))

    assert [trade.seller_agent_id for trade in trades] == ["A", "B"]
    assert [order.agent_id for order in book.asks] == ["B", "C"]


def test_momentum_holds_a_breakout_that_has_not_failed():
    agent = MomentumAgent("MOM", channel_length=5)
    for price in (100.0, 100.1, 99.9, 100.0, 100.05):
        agent.decide_action(_state(price))
    assert agent.decide_action(_state(100.3, recent_signed_volume=-300)) == []  # unconfirmed
    assert agent.decide_action(_state(100.5, recent_signed_volume=300))[0].side == OrderSide.BUY
    agent.position = 200
    agent.avg_entry_price = 100.5

    # Still above mid-channel: the old "back inside the channel" rule exited here.
    assert agent.decide_action(_state(100.4)) == []
    exit_orders = agent.decide_action(_state(99.9))
    assert exit_orders and exit_orders[0].side == OrderSide.SELL


def test_spoofer_pulls_the_layer_before_trading_against_it():
    agent = SpoofingAgent("SPOOF", spoof_duration_steps=2)
    agent.set_random_seed(1)
    spoof = agent.decide_action(_state(100.0))[0]

    while agent._state != SpoofingAgent.TRADING:
        agent.decide_action(_state(100.0))

    # The cancel is due at the start of the wakeup that sends the real trade.
    assert agent.cancel_for_state(_state(100.0)) == [spoof.order_id]
    real = agent.decide_action(_state(100.0))[0]
    assert real.order_type == OrderType.MARKET and real.side != spoof.side


def test_stop_dies_with_the_position_it_protected():
    agents = create_sandbox_agents("minimal", seed=3)
    sim = MarketSimulator(agents, seed=3)
    owner = agents[0]
    owner.position = 100
    sim._park_stop_order(Order(owner.agent_id, OrderSide.SELL, OrderType.STOP, 90.0, 100))

    owner.position = 0  # exited by other means
    sim._trigger_stop_orders()
    owner.position = 50  # a fresh position must not inherit the old stop
    sim.current_price = 89.0
    sim._trigger_stop_orders()

    assert sim._resting_stops == []
    assert all(event.callback != sim._process_order for event in sim.kernel.queue)


def test_a_run_that_reaches_the_close_leaves_a_session_report():
    sim = MarketSimulator([], duration_seconds=3, seed=1)
    sim.speed_multiplier = 20.0
    api_main._last_simulation_report = None
    try:
        asyncio.run(api_main._run_simulation_loop(sim))
        assert api_main._last_simulation_report is not None
        assert api_main._last_simulation_report["status"] == "completed"
        assert len(api_main._last_simulation_report["price_path"]) == 3
    finally:
        api_main._last_simulation_report = None
