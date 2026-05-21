import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.agents.risk import AgentRiskProfile
from backend.src.market.order import OrderSide


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
