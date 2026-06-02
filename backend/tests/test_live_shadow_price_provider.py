import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.market import simulator as simulator_module
from backend.src.agents.base_agent import BaseAgent
from backend.src.market.order import Order, OrderSide, OrderType
from backend.src.market.simulator import MarketSimulator


class PassiveTestAgent(BaseAgent):
    def __init__(self, agent_id: str = "TEST_AGENT"):
        super().__init__(agent_id, "Test", latency_seconds=0.0)

    def decide_action(self, market_state):
        return []


def test_live_shadow_external_price_provider_drives_price_and_book():
    quotes = [
        {"last_price": 101.25, "volume": 1200, "ltq": 15, "previous_close": 100.5},
        {"last_price": 102.0, "volume": 1500, "ltq": 20, "previous_close": 100.5},
    ]
    simulator = MarketSimulator([], initial_price=100.0, mode="LIVE_SHADOW")
    simulator.data_source = {"provider": "upstox", "source": "live_ltp", "status": "connected"}
    simulator.set_external_price_provider(lambda: quotes.pop(0), poll_interval_seconds=1)

    state = simulator.step()

    assert state["current_price"] == 101.25
    assert state["best_bid"] < 101.25
    assert state["best_ask"] > 101.25
    assert simulator.data_source["last_price"] == 101.25
    assert simulator.data_source["volume"] == 1200
    assert simulator.data_source["ltq"] == 15
    assert simulator.data_source["previous_close"] == 100.5
    assert simulator.data_source["status"] == "connected"


def test_live_shadow_external_depth_replaces_synthetic_order_book():
    quote = {
        "last_price": 101.25,
        "depth_source": "provider_live",
        "order_book": {
            "bids": [
                {"price": 101.2, "size": 300, "orders": 3},
                {"price": 101.15, "size": 200, "orders": 2},
            ],
            "asks": [
                {"price": 101.3, "size": 250, "orders": 4},
                {"price": 101.35, "size": 150, "orders": 1},
            ],
        },
    }
    simulator = MarketSimulator([], initial_price=100.0, mode="LIVE_SHADOW")
    simulator.data_source = {"provider": "upstox", "source": "live_depth", "status": "connected"}
    simulator.set_external_price_provider(lambda: quote, poll_interval_seconds=1)

    state = simulator.step()

    assert state["current_price"] == 101.25
    assert state["bid_levels"] == [
        {"price": 101.2, "size": 300},
        {"price": 101.15, "size": 200},
    ]
    assert state["ask_levels"] == [
        {"price": 101.3, "size": 250},
        {"price": 101.35, "size": 150},
    ]
    assert state["total_depth"] == 900
    assert simulator.data_source["depth_source"] == "provider_live"


def test_live_shadow_external_partial_depth_is_preserved():
    quote = {
        "last_price": 101.25,
        "depth_source": "provider_live",
        "order_book": {
            "bids": [],
            "asks": [
                {"price": 101.3, "size": 250, "orders": 4},
            ],
        },
    }
    simulator = MarketSimulator([], initial_price=100.0, mode="LIVE_SHADOW")
    simulator.data_source = {"provider": "upstox", "source": "live_depth", "status": "connected"}
    simulator.set_external_price_provider(lambda: quote, poll_interval_seconds=1)

    state = simulator.step()

    assert state["current_price"] == 101.25
    assert state["bid_levels"] == []
    assert state["ask_levels"] == [{"price": 101.3, "size": 250}]
    assert state["total_depth"] == 250


def test_live_shadow_external_price_errors_preserve_last_price():
    def failing_provider():
        raise RuntimeError("quote permission denied")

    simulator = MarketSimulator([], initial_price=100.0, mode="LIVE_SHADOW")
    simulator.data_source = {"provider": "upstox", "source": "live_ltp", "status": "connected"}
    simulator.set_external_price_provider(failing_provider, poll_interval_seconds=1)

    state = simulator.step()

    assert state["current_price"] == 100.0
    assert simulator.data_source["status"] == "error"
    assert "quote permission denied" in simulator.data_source["error"]


def test_live_shadow_external_provider_poll_interval_uses_wall_clock(monkeypatch):
    calls = 0

    def provider():
        nonlocal calls
        calls += 1
        return {"last_price": 101.0 + calls}

    monkeypatch.setattr(simulator_module.time, "monotonic", lambda: 100.0)
    simulator = MarketSimulator([], initial_price=100.0, mode="LIVE_SHADOW")
    simulator.data_source = {"provider": "upstox", "source": "live_ltp", "status": "connected"}
    simulator.set_external_price_provider(provider, poll_interval_seconds=1)

    first = simulator.step()
    second = simulator.step()

    assert calls == 1
    assert first["current_price"] == 102.0
    assert second["current_price"] == 102.0


def test_live_shadow_agent_orders_shadow_fill_without_moving_provider_price():
    agent = PassiveTestAgent()
    simulator = MarketSimulator([agent], initial_price=100.0, mode="LIVE_SHADOW")
    simulator.current_price = 101.25
    simulator.order_book.replace_depth(
        bids=[{"price": 101.2, "size": 100}],
        asks=[{"price": 101.3, "size": 80}],
    )

    simulator._process_order(
        Order(
            agent_id=agent.agent_id,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=101.25,
            quantity=40,
        )
    )
    simulator.kernel.run_until(simulator.current_time)

    assert simulator.current_price == 101.25
    assert len(simulator._all_trades) == 1
    assert simulator._all_trades[0].price == 101.3
    assert simulator._all_trades[0].quantity == 40
    assert agent.position == 40
    assert agent.num_trades == 1
    assert simulator.get_market_state()["recent_signed_volume"] == 40

    events = simulator.get_recent_events(limit=10)
    assert any(event["type"] == "order_submission" for event in events)
    assert any(event["type"] == "fill" for event in events)
    assert simulator.get_order_flow_summary()["fills"] == 1


def test_sandbox_signed_volume_uses_actual_fill_quantity():
    simulator = MarketSimulator([], initial_price=100.0, mode="SANDBOX")
    simulator.order_book.replace_depth(
        bids=[{"price": 99.9, "size": 50}],
        asks=[{"price": 100.1, "size": 30}],
    )

    simulator._process_order(
        Order(
            agent_id="TEST_AGENT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=100.0,
            quantity=100,
        )
    )

    assert len(simulator._all_trades) == 1
    assert simulator._all_trades[0].quantity == 30
    assert simulator.get_market_state()["recent_signed_volume"] == 30
