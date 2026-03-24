"""Normalization edge-case tests for provider input safety and signal compatibility."""

from __future__ import annotations

from collections import deque

from src.data.live_feed.base import FeedHealth
from src.data.live_feed.normalize import build_market_state
from src.prediction.signal_engine import SignalEngine, SignalInput


def test_missing_depth_levels_returns_none() -> None:
    state = build_market_state(
        step=1,
        current_time=1.0,
        duration_seconds=600,
        bids=[],
        asks=[{"price": 100.1, "size": 10.0}],
        price_history=[100.0, 100.1],
        signed_flow_history=deque([1.0], maxlen=10),
        recent_trades=[],
        recent_events=[],
    )
    assert state is None


def test_zero_spread_locked_book_is_supported() -> None:
    state = build_market_state(
        step=1,
        current_time=1.0,
        duration_seconds=600,
        bids=[{"price": 100.0, "size": 20.0}],
        asks=[{"price": 100.0, "size": 20.0}],
        price_history=[100.0, 100.0, 100.0],
        signed_flow_history=deque([0.0], maxlen=10),
        recent_trades=[],
        recent_events=[],
    )
    assert state is not None
    assert state.spread == 0.0
    assert state.mid_price == 100.0


def test_partial_or_empty_trade_lists_are_safe() -> None:
    state = build_market_state(
        step=2,
        current_time=2.0,
        duration_seconds=600,
        bids=[{"price": 100.0, "size": 20.0}],
        asks=[{"price": 100.2, "size": 25.0}],
        price_history=[99.9, 100.0, 100.1],
        signed_flow_history=deque([1.0, -2.0, 0.5], maxlen=10),
        recent_trades=[],
        recent_events=[],
    )
    assert state is not None
    assert state.recent_trades == []


def test_health_fields_allow_null_latency_and_timestamps() -> None:
    health = FeedHealth(
        connected=False,
        source="broker",
        provider="broker",
        last_update_ts=None,
        last_update_wall_time=None,
        fallback_active=True,
        stale=True,
        latency_ms=None,
        transport="poll",
        message="waiting_for_first_tick",
    )
    assert health.last_update_ts is None
    assert health.last_update_wall_time is None
    assert health.latency_ms is None
    assert health.stale is True


def test_signal_engine_accepts_safe_normalized_input() -> None:
    state = build_market_state(
        step=3,
        current_time=3.0,
        duration_seconds=600,
        bids=[{"price": 100.0, "size": 30.0}],
        asks=[{"price": 100.1, "size": 28.0}],
        price_history=[99.95, 100.0, 100.02, 100.05, 100.08, 100.1],
        signed_flow_history=deque([1.0, 2.0, -0.5], maxlen=10),
        recent_trades=[],
        recent_events=[],
    )
    assert state is not None

    engine = SignalEngine()
    result = engine.predict(
        SignalInput(
            mid_price=state.mid_price,
            spread=state.spread,
            order_book_imbalance=state.order_book_imbalance,
            recent_price_movement=state.recent_price_change,
            trade_flow=state.trade_flow,
            inventory=0.0,
        )
    )

    assert result["signal"] in {"BUY", "SELL", "HOLD"}
    assert 0.0 <= float(result["confidence"]) <= 1.0
    assert isinstance(result["explanation"], str)
