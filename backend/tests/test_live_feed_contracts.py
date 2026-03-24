"""Provider contract tests for normalized live-feed adapters."""

from __future__ import annotations

from collections import deque

from src.data.live_feed import (
    BinanceLiveFeedAdapter,
    BrokerAuthConfig,
    BrokerExchangeLiveFeedAdapter,
    MockLiveFeedAdapter,
    NseLikeLiveFeedAdapter,
)


REQUIRED_MARKET_STATE_KEYS = {
    "best_bid",
    "best_ask",
    "mid_price",
    "spread",
    "order_book_imbalance",
    "trade_flow",
    "volatility",
    "recent_trades",
}


def _assert_market_state_contract(state_dict: dict) -> None:
    missing = REQUIRED_MARKET_STATE_KEYS.difference(state_dict.keys())
    assert not missing, f"Missing MarketState fields: {sorted(missing)}"
    assert isinstance(state_dict["recent_trades"], list)


def _assert_health_contract(health, expected_provider: str) -> None:
    assert health.provider == expected_provider
    assert isinstance(health.stale, bool)
    assert health.latency_ms is None or health.latency_ms >= 0
    assert health.transport is None or isinstance(health.transport, str)


def test_mock_provider_contract() -> None:
    adapter = MockLiveFeedAdapter(initial_price=100.0, duration_seconds=600)

    import asyncio

    asyncio.run(adapter.start())
    state = adapter.latest_state()
    health = adapter.health()
    asyncio.run(adapter.stop())

    assert state is not None
    _assert_market_state_contract(state.to_dict())
    _assert_health_contract(health, expected_provider="mock")
    assert health.transport == "synthetic"


def test_binance_provider_contract_without_network() -> None:
    adapter = BinanceLiveFeedAdapter(symbol="btcusdt", duration_seconds=600)

    # Inject deterministic normalized inputs without external I/O.
    adapter._connected = True
    adapter._best_bid = 100.0
    adapter._best_ask = 100.1
    adapter._bids = [{"price": 100.0, "size": 12.0}, {"price": 99.9, "size": 8.0}]
    adapter._asks = [{"price": 100.1, "size": 10.0}, {"price": 100.2, "size": 9.0}]
    adapter._price_history.extend([99.8, 99.9, 100.0, 100.05, 100.0, 100.05, 100.1])
    adapter._signed_flow_history.extend([2.0, -1.0, 3.0])
    adapter._recent_trades.append(
        {
            "ts": 1.0,
            "trade_id": "t-1",
            "price": 100.05,
            "quantity": 3,
            "buyer_agent_id": "B",
            "seller_agent_id": "S",
            "aggressor_side": "BUY",
        }
    )

    state = adapter.latest_state()
    health = adapter.health()

    assert state is not None
    _assert_market_state_contract(state.to_dict())
    _assert_health_contract(health, expected_provider="binance")
    assert health.transport == "stream"


def test_nse_style_provider_contract_skeleton() -> None:
    adapter = NseLikeLiveFeedAdapter(symbol="nifty", duration_seconds=600)

    import asyncio

    asyncio.run(adapter.start())
    state = adapter.latest_state()
    health = adapter.health()
    asyncio.run(adapter.stop())

    # Skeleton does not emit market state yet, but health contract is enforced.
    assert state is None
    _assert_health_contract(health, expected_provider="nse")
    assert health.transport == "skeleton"


def test_broker_provider_contract_via_payload_normalization() -> None:
    adapter = BrokerExchangeLiveFeedAdapter(
        symbol="btcusdt",
        duration_seconds=600,
        stream_mode="poll",
        ws_url="",
        rest_url="https://example.com/feed",
        auth=BrokerAuthConfig(
            api_key="test-key",
            api_secret="",
            access_token="",
            account_id="",
        ),
        poll_interval_seconds=1.0,
        stale_after_seconds=6.0,
    )

    adapter._running = True
    adapter._transport = "poll"
    adapter._signed_flow_history = deque(maxlen=240)

    adapter._handle_payload(
        {
            "bids": [[100.0, 10], [99.9, 8]],
            "asks": [[100.1, 9], [100.2, 7]],
            "trades": [
                {"id": "x1", "price": 100.05, "qty": 2, "side": "BUY", "ts": 1.0},
                {"id": "x2", "price": 100.02, "qty": 1, "side": "SELL", "ts": 2.0},
            ],
        }
    )

    state = adapter.latest_state()
    health = adapter.health()

    assert state is not None
    _assert_market_state_contract(state.to_dict())
    _assert_health_contract(health, expected_provider="broker")
    assert health.transport == "poll"
