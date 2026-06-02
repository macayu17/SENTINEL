import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.agents.risk import AgentRiskProfile, risk_limited_order
from backend.src.market.order import OrderSide, OrderType


def test_agent_risk_profile_reduces_size_for_volatility_and_inventory_pressure():
    profile = AgentRiskProfile(
        max_inventory=1_000,
        base_order_size=200,
        min_order_size=10,
        participation_rate=0.10,
    )

    calm_size = profile.target_size(
        side=OrderSide.BUY,
        position=0,
        available_depth=5_000,
        volatility=0.001,
    )
    stressed_size = profile.target_size(
        side=OrderSide.BUY,
        position=850,
        available_depth=5_000,
        volatility=0.06,
    )

    assert calm_size == 200
    assert 10 <= stressed_size < calm_size


def test_agent_risk_profile_caps_orders_by_remaining_inventory_and_participation():
    profile = AgentRiskProfile(
        max_inventory=1_000,
        base_order_size=300,
        min_order_size=5,
        participation_rate=0.05,
    )

    assert profile.remaining_capacity(OrderSide.BUY, 975) == 25
    assert profile.remaining_capacity(OrderSide.SELL, -990) == 10
    assert profile.target_size(
        side=OrderSide.BUY,
        position=0,
        available_depth=1_000,
        volatility=0.0,
    ) == 50


def test_risk_limited_order_builds_order_from_market_depth_or_returns_none():
    profile = AgentRiskProfile(
        max_inventory=1_000,
        base_order_size=300,
        min_order_size=5,
        participation_rate=0.05,
    )
    market_state = {
        "ask_depth": 600,
        "bid_depth": 1_000,
    }

    order = risk_limited_order(
        profile,
        agent_id="A1",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=100.25,
        position=0,
        market_state=market_state,
        volatility=0.0,
    )

    assert order is not None
    assert order.agent_id == "A1"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.LIMIT
    assert order.price == 100.25
    assert order.quantity == 30

    blocked = risk_limited_order(
        profile,
        agent_id="A1",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=100.25,
        position=1_000,
        market_state=market_state,
        volatility=0.0,
    )

    assert blocked is None
