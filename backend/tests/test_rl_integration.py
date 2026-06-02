import builtins
import importlib
import sys
import types
from pathlib import Path

from backend.src.agents.rl_agent import RLAgent
from backend.src.market.simulator import MarketSimulator

PREDICTION_ROOT = Path(__file__).resolve().parents[1] / "src" / "prediction"


def _drop_intraday_rl_modules():
    for module_name in list(sys.modules):
        if module_name.startswith("backend.src.prediction.intraday_rl"):
            sys.modules.pop(module_name)


def test_intraday_environment_import_does_not_load_training_backend(monkeypatch):
    _drop_intraday_rl_modules()

    gymnasium_stub = types.ModuleType("gymnasium")
    gymnasium_stub.Env = object
    gymnasium_stub.spaces = types.SimpleNamespace(Box=object, Discrete=object)

    numpy_stub = types.ModuleType("numpy")
    numpy_stub.ndarray = object
    numpy_stub.float32 = "float32"
    numpy_stub.inf = float("inf")

    pandas_stub = types.ModuleType("pandas")
    pandas_stub.DataFrame = object
    pandas_stub.DatetimeIndex = object

    monkeypatch.setitem(sys.modules, "gymnasium", gymnasium_stub)
    monkeypatch.setitem(sys.modules, "numpy", numpy_stub)
    monkeypatch.setitem(sys.modules, "pandas", pandas_stub)

    prediction_pkg = types.ModuleType("backend.src.prediction")
    prediction_pkg.__path__ = [str(PREDICTION_ROOT)]
    src_pkg = importlib.import_module("backend.src")
    monkeypatch.setitem(sys.modules, "backend.src.prediction", prediction_pkg)
    monkeypatch.setattr(src_pkg, "prediction", prediction_pkg, raising=False)

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("stable_baselines3") or name == "torch" or name.startswith("torch."):
            raise AssertionError(f"eager training import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    try:
        module = importlib.import_module("backend.src.prediction.intraday_rl.environment")

        assert module.IntradayTradingEnv.__name__ == "IntradayTradingEnv"
    finally:
        _drop_intraday_rl_modules()


def test_rl_agent_routes_quotes_through_simulator_lifecycle():
    rl_agent = RLAgent("RL_MM", initial_capital=100000.0)
    simulator = MarketSimulator(agents=[rl_agent], initial_price=100.0, duration_seconds=10)
    simulator.reset(seed=7)

    rl_agent.set_action([-1.0, 0.0, -1.0])
    simulator.step()
    first_order_ids = set(rl_agent.active_orders.keys())
    book_order_ids = {order.order_id for order in simulator.order_book.bids + simulator.order_book.asks}

    assert simulator.step_count == 1
    assert len(first_order_ids) == 2
    assert first_order_ids.issubset(book_order_ids)
    assert rl_agent.consume_last_cancel_count() == 0

    rl_agent.set_action([1.0, 0.0, 1.0])
    simulator.step()
    second_order_ids = set(rl_agent.active_orders.keys())
    book_order_ids = {order.order_id for order in simulator.order_book.bids + simulator.order_book.asks}

    assert simulator.step_count == 2
    assert len(second_order_ids) == 2
    assert first_order_ids.isdisjoint(second_order_ids)
    assert first_order_ids.isdisjoint(book_order_ids)
    assert second_order_ids.issubset(book_order_ids)
    assert rl_agent.consume_last_cancel_count() == 2
