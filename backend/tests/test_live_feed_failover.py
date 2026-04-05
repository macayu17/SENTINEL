"""Failover and reconnect behavior tests for live-feed orchestration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from src.api import main
from src.data.live_feed.base import FeedHealth
from src.data.live_feed.mock_adapter import MockLiveFeedAdapter
from src.data.live_feed.normalize import build_market_state
from src.data.live_feed import broker_adapter as broker_module


class _FailingConnectContext:
    async def __aenter__(self) -> Any:
        raise RuntimeError("stream connect failed")

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FailingWebsockets:
    def connect(self, *args, **kwargs) -> _FailingConnectContext:
        return _FailingConnectContext()


class _CaptureManager:
    def __init__(self) -> None:
        self.client_count = 1
        self.updates: List[Dict[str, Any]] = []

    async def broadcast(self, update: Dict[str, Any]) -> None:
        self.updates.append(update)


class _StubLiveFeed:
    def __init__(self, *, connected: bool, stale: bool, provider: str = "broker") -> None:
        self._connected = connected
        self._stale = stale
        self._provider = provider

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def health(self) -> FeedHealth:
        return FeedHealth(
            connected=self._connected,
            source=self._provider,
            provider=self._provider,
            last_update_ts=1.0,
            last_update_wall_time=1.0,
            fallback_active=False,
            stale=self._stale,
            latency_ms=150.0,
            transport="stream",
            message="test_health",
        )

    def latest_state(self):
        if not self._connected:
            return None
        state = build_market_state(
            step=1,
            current_time=1.0,
            duration_seconds=600,
            bids=[{"price": 100.0, "size": 10.0}],
            asks=[{"price": 100.1, "size": 9.0}],
            price_history=[100.0, 100.1],
            signed_flow_history=[1.0],
            recent_trades=[],
            recent_events=[],
            recent_orders=[],
        )
        return state


def test_broker_stream_to_poll_fallback(monkeypatch) -> None:
    adapter = broker_module.BrokerExchangeLiveFeedAdapter(
        symbol="btcusdt",
        duration_seconds=600,
        stream_mode="auto",
        ws_url="wss://invalid.example",
        rest_url="https://example.com/market",
        auth=broker_module.BrokerAuthConfig(
            api_key="test",
            api_secret="",
            access_token="",
            account_id="",
        ),
        poll_interval_seconds=0.2,
        stale_after_seconds=6.0,
    )

    poll_called = {"value": False}

    async def _fake_poll_loop() -> None:
        poll_called["value"] = True
        adapter._running = False

    sleep_calls: List[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        return None

    monkeypatch.setattr(adapter, "_run_poll_loop", _fake_poll_loop)
    monkeypatch.setattr(broker_module, "websockets", _FailingWebsockets())
    monkeypatch.setattr(broker_module.asyncio, "sleep", _fake_sleep)

    adapter._running = True
    asyncio.run(adapter._run_stream_loop())

    assert poll_called["value"], "Expected stream mode fallback to polling mode"
    assert sleep_calls and sleep_calls[0] == adapter.reconnect_base_delay


def test_broker_reconnect_backoff_on_poll_errors(monkeypatch) -> None:
    adapter = broker_module.BrokerExchangeLiveFeedAdapter(
        symbol="btcusdt",
        duration_seconds=600,
        stream_mode="poll",
        ws_url="",
        rest_url="https://example.com/market",
        auth=broker_module.BrokerAuthConfig(
            api_key="test",
            api_secret="",
            access_token="",
            account_id="",
        ),
        poll_interval_seconds=0.2,
        stale_after_seconds=6.0,
        reconnect_base_delay=1.0,
        reconnect_max_delay=8.0,
    )

    def _failing_fetch() -> Dict[str, Any]:
        raise RuntimeError("poll endpoint unavailable")

    sleep_calls: List[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        adapter._running = False

    monkeypatch.setattr(adapter, "_fetch_poll_payload", _failing_fetch)
    monkeypatch.setattr(broker_module.asyncio, "sleep", _fake_sleep)

    adapter._running = True
    asyncio.run(adapter._run_poll_loop())

    assert sleep_calls and sleep_calls[0] == 1.0
    assert "poll_reconnect_attempt_1" in adapter.health().message


def test_live_shadow_real_to_mock_fallback_without_crash(monkeypatch) -> None:
    fake_manager = _CaptureManager()
    live_feed = _StubLiveFeed(connected=False, stale=False, provider="broker")

    mock_feed = MockLiveFeedAdapter(initial_price=100.0, duration_seconds=600)
    asyncio.run(mock_feed.start())

    monkeypatch.setattr(main, "manager", fake_manager)
    monkeypatch.setattr(main, "_live_feed", live_feed)
    monkeypatch.setattr(main, "_mock_live_feed", mock_feed)
    monkeypatch.setattr(main, "_live_fallback_active", False)
    monkeypatch.setattr(main, "_active_live_source", "broker")

    async def _run_once_then_cancel() -> None:
        task = asyncio.create_task(main._run_live_shadow_loop())
        await asyncio.sleep(0.35)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run_once_then_cancel())
    asyncio.run(mock_feed.stop())

    assert fake_manager.updates, "Expected websocket updates while fallback active"
    update = fake_manager.updates[-1]
    assert update["live_feed"]["source"] == "mock"
    assert update["live_feed"]["fallback_active"] is True


def test_live_shadow_stale_detection_triggers_fallback(monkeypatch) -> None:
    fake_manager = _CaptureManager()
    live_feed = _StubLiveFeed(connected=True, stale=True, provider="broker")

    mock_feed = MockLiveFeedAdapter(initial_price=100.0, duration_seconds=600)
    asyncio.run(mock_feed.start())

    monkeypatch.setattr(main, "manager", fake_manager)
    monkeypatch.setattr(main, "_live_feed", live_feed)
    monkeypatch.setattr(main, "_mock_live_feed", mock_feed)
    monkeypatch.setattr(main, "_live_fallback_active", False)
    monkeypatch.setattr(main, "_active_live_source", "broker")

    async def _run_once_then_cancel() -> None:
        task = asyncio.create_task(main._run_live_shadow_loop())
        await asyncio.sleep(0.35)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run_once_then_cancel())
    asyncio.run(mock_feed.stop())

    assert fake_manager.updates, "Expected websocket updates while stale fallback is active"
    update = fake_manager.updates[-1]
    assert update["live_feed"]["source"] == "mock"
    assert update["live_feed"]["fallback_active"] is True
    assert update["live_feed"]["stale"] is False
