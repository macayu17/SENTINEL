import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.data.historical import parse_nse_csv
from backend.src.market.simulator import MarketSimulator


def test_imports_nse_quote_history_with_comma_formatted_numbers():
    dataset = parse_nse_csv(
        'DATE,SERIES,OPEN,HIGH,LOW,PREV. CLOSE,LTP,CLOSE,VWAP\n'
        '20-Nov-2026,EQ,"1,369.00","1,383.00","1,356.10","1,375.60","1,377.50","1,377.50","1,366.90"\n'
        '19-Nov-2026,EQ,"1,361.90","1,382.50","1,349.70","1,363.00","1,375.60","1,375.60","1,368.14"\n',
        filename="Quote-Equity-RELIANCE.csv",
        dataset_id="quote",
    )

    assert len(dataset.points) == 2
    assert dataset.symbol == "RELIANCE"
    assert dataset.points[0].price == pytest.approx(1377.50)


def test_imports_chart_rows_with_duplicate_headers_and_sparse_price_columns():
    dataset = parse_nse_csv(
        '"DateTime","Pre Open RELIANCEEQN","RELIANCEEQN","Indicative Close RELIANCEEQN","RELIANCEEQN"\n'
        '"2026-11-20 09:00:59",1360,,,\n'
        '"2026-11-20 10:03:59",,1361.9,,\n'
        '"2026-11-20 15:59:39",,,,1377.5\n',
        filename="chart.csv",
        dataset_id="chart",
    )

    assert [point.price for point in dataset.points] == [1360, 1361.9, 1377.5]


def test_historical_replay_keeps_reference_path_and_run_metadata():
    simulator = MarketSimulator([], initial_price=100, duration_seconds=2, historical_prices=[100, 101, 99], historical_dataset_id="demo")
    assert simulator.get_export_snapshot()["run_config"]["historical_replay"] is True
    simulator.running = True
    assert simulator.step()["current_price"] == 101
    assert simulator.step()["current_price"] == 99
