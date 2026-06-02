from backend.src.agents.hft_agent import HFTAgent
from backend.src.agents.informed import InformedAgent
from backend.src.agents.institutional import InstitutionalAgent
from backend.src.agents.liquidity_trader import LiquidityTraderAgent
from backend.src.agents.market_maker import MarketMakerAgent
from backend.src.agents.mean_reversion import MeanReversionAgent
from backend.src.agents.momentum import MomentumAgent
from backend.src.agents.noise import NoiseAgent
from backend.src.agents.retail import RetailAgent
from backend.src.agents.sentiment import SentimentAgent
from backend.src.agents.spoofing import SpoofingAgent
from backend.src.market.order import OrderSide, OrderType


def _state(**overrides):
    state = {
        "mid_price": 100.0,
        "current_price": 100.0,
        "spread": 0.02,
        "bid_depth": 5_000,
        "ask_depth": 5_000,
        "volatility": 0.001,
        "order_book_imbalance": 0.0,
        "recent_signed_volume": 0,
        "recent_price_change": 0.0,
        "current_time": 120.0,
        "time_to_close": 10_000,
    }
    state.update(overrides)
    return state


def test_realistic_agents_expose_shared_risk_profile():
    agents = [
        MarketMakerAgent("MM"),
        HFTAgent("HFT"),
        InstitutionalAgent("INST"),
        RetailAgent("RET"),
        NoiseAgent("NOISE"),
        InformedAgent("INF"),
        MomentumAgent("MOM"),
        MeanReversionAgent("MR"),
        SentimentAgent("SENT"),
        LiquidityTraderAgent("LIQ"),
        SpoofingAgent("SPOOF"),
    ]

    for agent in agents:
        assert hasattr(agent, "risk_profile"), agent.agent_type
        assert agent.risk_profile.max_inventory > 0
        assert agent.risk_profile.base_order_size > 0


def test_market_maker_widens_quotes_in_high_volatility():
    calm = MarketMakerAgent("MM_CALM", base_spread=0.001, quote_size=200)
    stressed = MarketMakerAgent("MM_STRESS", base_spread=0.001, quote_size=200)

    calm_orders = calm.decide_action(_state(volatility=0.001))
    stress_orders = stressed.decide_action(_state(volatility=0.08))

    calm_width = max(order.price for order in calm_orders) - min(order.price for order in calm_orders)
    stress_width = max(order.price for order in stress_orders) - min(order.price for order in stress_orders)

    assert stress_width > calm_width


def test_market_maker_near_inventory_cap_only_quotes_flattening_side():
    agent = MarketMakerAgent("MM_CAP", quote_size=200, max_inventory=1_000)
    agent.position = 950

    orders = agent.decide_action(_state())

    assert orders
    assert all(order.side == OrderSide.SELL for order in orders)


def test_institutional_child_order_respects_participation_of_displayed_depth():
    agent = InstitutionalAgent(
        "INST",
        target_quantity=50_000,
        execution_window=3_600,
        slice_interval=60,
        max_slice_size=1_000,
    )
    agent.side = OrderSide.BUY
    agent._started = True
    agent._last_slice_time = 0.0

    orders = agent.decide_action(_state(current_time=61.0, ask_depth=500, spread=0.02))

    assert len(orders) == 1
    assert orders[0].order_type in {OrderType.LIMIT, OrderType.MARKET}
    assert orders[0].quantity <= 75
