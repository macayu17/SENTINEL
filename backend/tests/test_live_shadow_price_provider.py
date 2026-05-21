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
