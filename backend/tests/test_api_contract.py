import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.api import main as api_main


def test_invalid_simulation_mode_returns_bad_request():
    client = TestClient(api_main.app)

    response = client.post("/api/simulation/mode", json={"mode": "INVALID"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid mode"


def test_market_data_endpoints_require_active_simulation():
    api_main.simulator = None
    client = TestClient(api_main.app)

    for path in [
        "/api/prediction/liquidity",
        "/api/prediction/large-order",
        "/api/agents/metrics",
        "/api/market/snapshot",
    ]:
        response = client.get(path)
        assert response.status_code == 409
        assert response.json()["detail"] == "No active simulation"
