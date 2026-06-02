import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.market.market_data import StockInfo, build_oracle_path


def test_build_oracle_path_extends_with_bar_return_volatility():
    info = StockInfo(
        ticker="NSE-WIPRO",
        name="NSE-WIPRO Groww CASH",
        currency="INR",
        last_close=100.0,
        period_start="2025-09-24T09:15:00",
        period_end="2025-09-24T10:15:00",
        bars=3,
        prices=[100.0, 110.0, 100.0],
        volumes=[1000, 1200, 1300],
        highs=[101.0, 111.0, 101.0],
        lows=[99.0, 109.0, 99.0],
        returns=[0.10, -0.10],
        realized_vol=0.80,
        mean_return=0.0,
    )

    path = build_oracle_path(info, target_steps=4)

    expected_sigma = 100.0 * 0.10
    expected_next = 100.0 + expected_sigma * 0.4967141530112327
    assert path == pytest.approx([100.0, 110.0, 100.0, expected_next])
