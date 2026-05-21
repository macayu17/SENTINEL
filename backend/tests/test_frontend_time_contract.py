from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRICE_CHART = ROOT / "frontend" / "components" / "PriceChart.tsx"
MARKET_STORE = ROOT / "frontend" / "store" / "market-store.ts"
DASHBOARD_PAGE = ROOT / "frontend" / "app" / "dashboard" / "page.tsx"


def test_price_chart_formats_market_time_in_ist():
    source = PRICE_CHART.read_text(encoding="utf-8")

    assert "Asia/Kolkata" in source
    assert "formatChartTime" in source
    assert "period_start" in source
    assert "period_end" in source


def test_market_store_tracks_receive_time_for_live_chart_ticks():
    source = MARKET_STORE.read_text(encoding="utf-8")

    assert "receivedAt" in source
    assert "Date.now()" in source


def test_dashboard_clock_uses_ist():
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")

    assert "formatISTWallClock" in source
    assert "Asia/Kolkata" in source
