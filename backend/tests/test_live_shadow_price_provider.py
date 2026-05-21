import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.market.simulator import MarketSimulator


def test_live_shadow_external_price_provider_drives_price_and_book():
    quotes = [
        {"last_price": 101.25, "volume": 1200, "ltq": 15, "previous_close": 100.5},
        {"last_price": 102.0, "volume": 1500, "ltq": 20, "previous_close": 100.5},
    ]
    simulator = MarketSimulator([], initial_price=100.0, mode="LIVE_SHADOW")
    simulator.data_source = {"provider": "upstox", "source": "live_ltp", "status": "connected"}
    simulator.set_external_price_provider(lambda: quotes.pop(0), poll_interval_steps=1)

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
    simulator.set_external_price_provider(lambda: quote, poll_interval_steps=1)

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
    simulator.set_external_price_provider(lambda: quote, poll_interval_steps=1)

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
    simulator.set_external_price_provider(failing_provider, poll_interval_steps=1)

    state = simulator.step()

    assert state["current_price"] == 100.0
    assert simulator.data_source["status"] == "error"
    assert "quote permission denied" in simulator.data_source["error"]
