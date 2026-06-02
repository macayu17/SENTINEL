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
from backend.src.market.order import Order, OrderSide, OrderType


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


def test_market_maker_close_flattening_is_depth_capped():
    agent = MarketMakerAgent("MM_CLOSE", quote_size=500, max_inventory=5_000)
    agent.position = 2_000

    orders = agent.decide_action(_state(time_to_close=120, bid_depth=300, ask_depth=5_000))

    assert len(orders) == 1
    assert orders[0].side == OrderSide.SELL
    assert orders[0].order_type == OrderType.MARKET
    assert orders[0].quantity == 24


def test_market_maker_reduces_passive_bid_when_bid_queue_is_crowded():
    agent = MarketMakerAgent("MM_QUEUE", quote_size=500, max_inventory=5_000)

    balanced_orders = agent.decide_action(_state(bid_depth=5_000, ask_depth=5_000, order_book_imbalance=0.0))
    crowded_orders = agent.decide_action(_state(bid_depth=50_000, ask_depth=1_000, order_book_imbalance=0.9))

    balanced_bid = next(order for order in balanced_orders if order.side == OrderSide.BUY)
    crowded_bid = next(order for order in crowded_orders if order.side == OrderSide.BUY)
    crowded_ask = next(order for order in crowded_orders if order.side == OrderSide.SELL)

    assert crowded_bid.quantity < balanced_bid.quantity
    assert crowded_ask.quantity >= crowded_bid.quantity


def test_market_maker_keeps_fresh_quotes_and_cancels_stale_quotes():
    agent = MarketMakerAgent("MM_STALE", base_spread=0.001, quote_size=200)
    first_orders = agent.decide_action(_state())
    assert len(first_orders) == 2

    agent.active_orders = {order.order_id: order for order in first_orders}

    assert agent.cancel_for_state(_state()) == []
    assert agent.decide_action(_state()) == []

    cancellations = agent.cancel_for_state(_state(mid_price=101.0, current_price=101.0))

    assert set(cancellations) == {order.order_id for order in first_orders}


def test_hft_imbalance_scalp_does_not_wait_for_price_history_warmup():
    agent = HFTAgent("HFT_IMB")

    orders = agent.decide_action(_state(order_book_imbalance=0.65, spread=0.04))

    assert orders
    assert orders[0].side == OrderSide.BUY
    assert orders[0].order_type == OrderType.LIMIT


def test_hft_keeps_fresh_scalp_order_until_reprice():
    agent = HFTAgent("HFT_KEEP")
    state = _state(order_book_imbalance=0.65, spread=0.04)
    first_orders = agent.decide_action(state)
    assert len(first_orders) == 1

    agent.active_orders = {first_orders[0].order_id: first_orders[0]}

    assert agent.cancel_for_state(state) == []
    assert agent.decide_action(state) == []

    cancellations = agent.cancel_for_state(_state(mid_price=101.0, current_price=101.0, order_book_imbalance=0.65, spread=0.04))

    assert cancellations == [first_orders[0].order_id]


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


def test_institutional_child_limit_persists_until_stale_threshold():
    agent = InstitutionalAgent(
        "INST_KEEP",
        target_quantity=10_000,
        execution_window=1_200,
        slice_interval=30,
        max_slice_size=500,
        start_after_seconds=0.0,
    )
    agent.side = OrderSide.BUY
    first_orders = agent.decide_action(_state(current_time=31.0, ask_depth=2_000))
    assert len(first_orders) == 1
    agent.active_orders = {first_orders[0].order_id: first_orders[0]}

    assert agent.cancel_for_state(_state(current_time=40.0, ask_depth=2_000)) == []
    assert agent.decide_action(_state(current_time=40.0, ask_depth=2_000)) == []

    assert agent.cancel_for_state(_state(current_time=40.0, mid_price=101.0, current_price=101.0, ask_depth=2_000)) == [
        first_orders[0].order_id
    ]


def test_institutional_agent_can_start_on_scheduled_delay_without_random_gate():
    agent = InstitutionalAgent(
        "INST_SCHEDULED",
        target_quantity=10_000,
        execution_window=1_200,
        slice_interval=30,
        max_slice_size=500,
        start_after_seconds=10.0,
    )
    agent.side = OrderSide.SELL

    assert agent.decide_action(_state(current_time=9.0)) == []

    orders = agent.decide_action(_state(current_time=41.0, bid_depth=2_000, ask_depth=2_000))

    assert len(orders) == 1
    assert orders[0].side == OrderSide.SELL
    assert orders[0].quantity > 0


def test_liquidity_trader_keeps_fresh_child_limit_until_reprice():
    agent = LiquidityTraderAgent("LIQ_KEEP")
    agent._active_side = OrderSide.BUY
    resting = Order("LIQ_KEEP", OrderSide.BUY, OrderType.LIMIT, 99.99, 100)
    agent.active_orders = {resting.order_id: resting}

    assert agent.cancel_for_state(_state(spread=0.02)) == []
    assert agent.cancel_for_state(_state(mid_price=101.0, current_price=101.0, spread=0.02)) == [resting.order_id]


def test_mean_reversion_keeps_fresh_entry_limit_until_reprice():
    agent = MeanReversionAgent("MR_KEEP")
    resting = Order("MR_KEEP", OrderSide.BUY, OrderType.LIMIT, 100.01, 100)
    agent.active_orders = {resting.order_id: resting}

    assert agent.cancel_for_state(_state()) == []
    assert agent.cancel_for_state(_state(mid_price=101.0, current_price=101.0)) == [resting.order_id]
