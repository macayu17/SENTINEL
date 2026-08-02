import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.agents.noise import NoiseAgent
from backend.src.agents.risk import enforce_trading_rules
from backend.src.market.order import Order, OrderSide, OrderType


def _agent(position: int = 0, capital: float = 20_000.0) -> NoiseAgent:
    agent = NoiseAgent("noise_test", initial_capital=capital)
    agent.position = position
    agent.avg_entry_price = 100.0 if position else 0.0
    return agent


def _order(side: OrderSide, quantity: int, order_type=OrderType.MARKET, price: float = 100.0) -> Order:
    return Order("noise_test", side, order_type, price, quantity)


STATE = {"mid_price": 100.0, "session_phase": "CONTINUOUS"}


def test_price_collar_rejects_far_limit_orders():
    agent = _agent()
    far = _order(OrderSide.BUY, 10, OrderType.LIMIT, price=110.0)
    near = _order(OrderSide.BUY, 10, OrderType.LIMIT, price=101.0)

    accepted, rejected = enforce_trading_rules(agent, [far, near], STATE)

    assert [o.price for o in accepted] == [101.0]
    assert rejected == [(far, "price_collar")]


def test_leverage_cap_clips_and_then_rejects_batch_orders():
    # 20k capital at 2x leverage and mid 100 → 400 shares max exposure.
    agent = _agent()
    first = _order(OrderSide.BUY, 1_000)
    second = _order(OrderSide.BUY, 50)

    accepted, rejected = enforce_trading_rules(agent, [first, second], STATE)

    assert accepted == [first]
    assert first.quantity == 400
    assert rejected == [(second, "leverage_cap")]


def test_leverage_cap_counts_resting_same_side_orders():
    agent = _agent(position=200)
    resting = _order(OrderSide.BUY, 150, OrderType.LIMIT, price=99.0)
    agent.active_orders[resting.order_id] = resting

    accepted, _ = enforce_trading_rules(agent, [_order(OrderSide.BUY, 500)], STATE)

    assert accepted[0].quantity == 50  # 400 - 200 held - 150 resting


def test_drawdown_kill_switch_latches_and_allows_reduce_only():
    agent = _agent(position=200)
    agent.realized_pnl = -6_000.0  # 30% drawdown on 20k

    opening = _order(OrderSide.BUY, 50)
    flip = _order(OrderSide.SELL, 500)
    accepted, rejected = enforce_trading_rules(agent, [opening, flip], STATE)

    assert agent.risk_halted is True
    assert rejected == [(opening, "risk_halted")]
    assert accepted == [flip]
    assert flip.quantity == 200  # reduce-only: clipped at flat, no flip

    agent.reset()
    assert agent.risk_halted is False


def test_close_phase_halves_opening_size_but_not_exits():
    close_state = {"mid_price": 100.0, "session_phase": "CLOSE"}

    opening = _order(OrderSide.BUY, 100)
    accepted, _ = enforce_trading_rules(_agent(), [opening], close_state)
    assert accepted[0].quantity == 50

    exit_order = _order(OrderSide.SELL, 100)
    accepted, _ = enforce_trading_rules(_agent(position=100), [exit_order], close_state)
    assert accepted[0].quantity == 100
