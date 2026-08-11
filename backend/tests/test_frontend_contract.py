from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SANDBOX_PANEL = ROOT / "frontend" / "components" / "dashboard" / "SandboxControlPanel.tsx"
DASHBOARD_PAGE = ROOT / "frontend" / "app" / "dashboard" / "page.tsx"
API_CLIENT = ROOT / "frontend" / "lib" / "api-client.ts"
MARKET_STORE = ROOT / "frontend" / "store" / "market-store.ts"
MARKET_TYPES = ROOT / "frontend" / "types" / "market.ts"
API_MAIN = ROOT / "backend" / "src" / "api" / "main.py"
API_TYPES = ROOT / "frontend" / "types" / "api.ts"
WEBSOCKET = ROOT / "frontend" / "lib" / "websocket.ts"
DASHBOARD_DATA = ROOT / "frontend" / "lib" / "dashboard-data.ts"
THEME_TOGGLE = ROOT / "frontend" / "components" / "ThemeToggle.tsx"
DEAD_DASHBOARD_COMPONENTS = (
    "AgentActivityPanel.tsx",
    "DepthHeatmapPanel.tsx",
    "EventLogPanel.tsx",
    "MetricCard.tsx",
    "MilestoneTracker.tsx",
    "PriceSpreadChart.tsx",
    "ProjectOverviewPanel.tsx",
    "SectionCard.tsx",
    "SeriesChartPanel.tsx",
    "TradeFlowChart.tsx",
)


def test_live_shadow_workflow_is_removed_from_frontend():
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SANDBOX_PANEL, DASHBOARD_PAGE, API_CLIENT, API_TYPES, MARKET_STORE, MARKET_TYPES)
    )

    for removed_surface in ("LIVE SHADOW", "LIVE_SHADOW", "/api/live-shadow", "startUpstox", "UpstoxReplayRequest"):
        assert removed_surface not in sources


def test_dashboard_has_light_mode_toggle_and_global_theme_class():
    page_source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    toggle_source = THEME_TOGGLE.read_text(encoding="utf-8")
    css_source = (ROOT / "frontend" / "app" / "globals.css").read_text(encoding="utf-8")

    assert "<ThemeToggle />" in page_source
    assert "sentinel-theme" in toggle_source
    assert "theme-light" in toggle_source
    assert "html.theme-light" in css_source


def test_frontend_exposes_simulation_export_endpoint():
    source = API_CLIENT.read_text(encoding="utf-8")

    assert "exportSimulation" in source
    assert "/api/simulation/export" in source


def test_api_request_contract_types_are_shared_outside_client():
    api_source = API_CLIENT.read_text(encoding="utf-8")

    assert API_TYPES.exists()
    api_types_source = API_TYPES.read_text(encoding="utf-8")
    assert "from '@/types/api'" in api_source
    assert "} from '@/types/api';" in api_source
    for type_name in (
        "LatencyMode",
        "SandboxPreset",
        "SandboxScenario",
        "SandboxCreateRequest",
    ):
        assert f"export interface {type_name}" not in api_source
        assert f"export type {type_name}" not in api_source
        assert type_name in api_types_source


def test_api_client_has_no_redundant_mode_or_default_start_commands():
    source = API_CLIENT.read_text(encoding="utf-8")

    assert "async setSimulationMode" not in source
    assert "async startSimulation" not in source


def test_api_client_reports_backend_offline_with_start_command():
    source = API_CLIENT.read_text(encoding="utf-8")

    assert "Backend unavailable at" in source
    assert "py -3.11 -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000" in source


def test_dashboard_header_does_not_bypass_sandbox_control_panel():
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")

    assert "handleStartStop" not in source
    assert "api.startSimulation()" not in source
    assert "api.stopSimulation()" not in source


def test_market_store_bounds_history_and_alerts_without_unneeded_array_churn():
    source = MARKET_STORE.read_text(encoding="utf-8")

    assert "appendBoundedPricePoint" in source
    assert "buildNextAlerts" in source
    assert "return state.alerts;" in source
    assert "history.shift()" not in source


def test_sandbox_panel_has_export_command_for_running_runs():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "exportSimulation" in source
    assert "EXPORT" in source
    assert "URL.createObjectURL" in source


def test_sandbox_panel_uses_native_sized_control_affordances():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "const FIELD_CLASS" in source
    assert "h-10 w-full" in source
    assert '<input type="number"' in source
    assert "<select" in source


def test_balanced_preset_includes_liquidity_execution_agent():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "LiquidityTrader: 1" in source


def test_frontend_exposes_only_native_sim_workflow():
    panel_source = SANDBOX_PANEL.read_text(encoding="utf-8")
    api_types_source = API_TYPES.read_text(encoding="utf-8")
    api_client_source = API_CLIENT.read_text(encoding="utf-8")

    for removed_surface in ("groww", "abides", "RL_MM", "rlPaper", "yfinance"):
        assert removed_surface.lower() not in panel_source.lower()

    for removed_method in (
        "getSandboxCapabilities",
        "createAbidesSandbox",
        "startGrowwReplay",
        "startGrowwLive",
        "setAbidesSpeed",
    ):
        assert f"async {removed_method}" not in api_client_source

    for removed_type in (
        "AbidesSandboxCreateRequest",
        "GrowwReplayRequest",
        "GrowwLiveRequest",
    ):
        assert removed_type not in api_types_source


def test_dashboard_has_one_sim_control_path_and_no_orphan_components():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")
    dashboard_components = SANDBOX_PANEL.parent

    assert "<ToggleButton active={engine === 'groww'}" not in source
    assert "<ToggleButton active={engine === 'abides'}" not in source
    assert 'label="SYMBOL SEARCH"' not in source
    assert 'label="INSTRUMENT KEY"' not in source
    assert "{inLiveControl ? (" not in source
    assert "!inLiveControl && engine !== 'abides'" not in source
    for filename in DEAD_DASHBOARD_COMPONENTS:
        assert not (dashboard_components / filename).exists()


def test_sandbox_launch_uses_one_creation_request_and_loads_metadata_once():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "api.setSimulationMode" not in source
    assert "api.startSimulation" not in source
    assert source.count("api.getSandboxPresets()") == 1
    assert source.count("api.getSandboxScenarios()") == 1


def test_dashboard_data_keeps_only_rendered_runtime_state():
    source = DASHBOARD_DATA.read_text(encoding="utf-8")

    for unused_name in (
        "defaultMilestones",
        "projectOverview",
        "priceSeries",
        "spreadSeries",
        "inventorySeries",
        "rewardSeries",
        "depthHeatmap",
    ):
        assert unused_name not in source


def test_frontend_omits_dead_client_store_and_stitch_surfaces():
    client_source = API_CLIENT.read_text(encoding="utf-8")
    store_source = MARKET_STORE.read_text(encoding="utf-8")

    for unused_method in (
        "fetchGrowwHistorical",
        "fetchGrowwQuote",
        "fetchUpstoxHistorical",
        "fetchUpstoxLtp",
        "getLiquidityPrediction",
        "getLargeOrderDetection",
        "getAgentMetrics",
        "getMarketSnapshot",
    ):
        assert f"async {unused_method}" not in client_source

    assert "addAlert:" not in store_source
    assert "clearAlerts:" not in store_source
    assert not (ROOT / "frontend" / "lib" / "stitch-mcp.ts").exists()


def test_sandbox_panel_exposes_scenario_selection():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "api.getSandboxScenarios" in source
    assert "scenario" in source
    assert "SCENARIO" in source
    assert "scenarios.map" in source


def test_market_update_trace_fields_are_typed_and_normalized():
    types_source = MARKET_TYPES.read_text(encoding="utf-8")
    websocket_source = WEBSOCKET.read_text(encoding="utf-8")

    assert "export interface MarketEvent" in types_source
    assert "export interface MarketOrderFlow" in types_source
    assert "export interface MarketRecentOrder" in types_source
    assert "events?: MarketEvent[]" in types_source
    assert "order_flow?: MarketOrderFlow" in types_source
    assert "recent_orders?: MarketRecentOrder[]" in types_source
    assert "events: data.events ?? []" in websocket_source
    assert "order_flow: data.order_flow" in websocket_source
    assert "recent_orders: data.recent_orders ?? []" in websocket_source
    assert "session_phase: string;" in types_source
    assert "activity_multiplier: number;" in types_source
    assert "scenario: MarketScenario;" in types_source
    assert "latency_mode: string;" in types_source
    assert "session_phase: data.session_phase" in websocket_source
    assert "activity_multiplier: finiteNumber(data.activity_multiplier, 1)" in websocket_source


def test_dashboard_exposes_causal_sim_state_and_oracle_price_overlay():
    dashboard_source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    chart_source = (ROOT / "frontend" / "components" / "PriceChart.tsx").read_text(encoding="utf-8")
    store_source = MARKET_STORE.read_text(encoding="utf-8")

    for label in (
        "CAUSAL MARKET STATE",
        "REGIME",
        "SESSION",
        "ACTIVITY",
        "LATENCY",
        "LATENT VALUE",
        "REFERENCE GAP",
        "AGGRESSOR FLOW",
    ):
        assert label in dashboard_source

    assert "if (hasOracle)" in dashboard_source
    assert 'dataKey="fundamental"' in chart_source
    assert "fundamental: data.oracle?.fundamental_value" in store_source


def test_sandbox_uses_informed_access_without_manual_oracle_tuning_controls():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "INFORMED ACCESS" in source
    assert "ORACLE ACCESS" not in source
    assert 'label="KAPPA"' not in source
    assert 'label="SIGMA"' not in source
    assert "oracle_kappa:" not in source
    assert "oracle_sigma:" not in source


def test_dashboard_clock_and_order_rows_do_not_emit_react_runtime_issues():
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")

    assert "useState<Date | null>(null)" in source
    assert "now ? formatISTWallClock(now) : '--:--:--'" in source
    assert "activity.recentOrders.map((order, index)" in source
    assert "key={`${order.id}-${order.status}-${index}`}" in source


def test_liquidity_panel_labels_untrained_output_as_current_stress():
    source = (ROOT / "frontend" / "components" / "LiquidityGauge.tsx").read_text(
        encoding="utf-8"
    )
    types_source = MARKET_TYPES.read_text(encoding="utf-8")

    assert "CURRENT STRESS" in source
    assert "pred.stress_score" in source
    assert "const probability = pred.probability" not in source
    assert "stress_score: number;" in types_source
    assert '"adaptive_stress"' in types_source


def test_websocket_batches_market_updates_without_background_tab_stalls():
    source = WEBSOCKET.read_text(encoding="utf-8")

    assert "setTimeout(flushLatestUpdate, 16)" in source
    assert "requestAnimationFrame" not in source
    assert "WebSocket.CONNECTING" in source
    assert "setTimeout(flushLatestUpdate, 250)" not in source


def test_sim_frontend_removes_custom_agent_editor_and_legacy_mode_state():
    panel = SANDBOX_PANEL.read_text(encoding="utf-8")
    api_types = API_TYPES.read_text(encoding="utf-8")
    market_types = MARKET_TYPES.read_text(encoding="utf-8")
    store = MARKET_STORE.read_text(encoding="utf-8")

    assert "customAgentsEnabled" not in panel
    assert "updateAgentCount" not in panel
    assert "custom_agents" not in api_types
    assert "SimulationMode" not in market_types
    assert "MarketDataSource" not in market_types
    assert "simulationMode" not in store


def test_dashboard_trace_panels_prefer_backend_market_update_fields():
    source = DASHBOARD_DATA.read_text(encoding="utf-8")

    assert "mapBackendEvents" in source
    assert "buildBackendAgentActivity" in source
    assert "marketData.events" in source
    assert "marketData.order_flow" in source
    assert "marketData.recent_orders" in source
    assert "setTradeFlow((previous) => mergeBackendTradeFlow" in source
    assert "setEvents(mapBackendEvents(marketData.events))" in source


def test_frontend_does_not_fabricate_or_overclaim_market_signals():
    order_book_source = (ROOT / "frontend" / "components" / "OrderBookHeatmap.tsx").read_text(encoding="utf-8")
    liquidity_source = (ROOT / "frontend" / "components" / "LiquidityGauge.tsx").read_text(encoding="utf-8")
    large_order_source = (ROOT / "frontend" / "components" / "LargeOrderDetector.tsx").read_text(encoding="utf-8")
    agent_source = (ROOT / "frontend" / "components" / "AgentMetricsPanel.tsx").read_text(encoding="utf-8")
    dashboard_source = DASHBOARD_DATA.read_text(encoding="utf-8")

    assert "buildFallbackSide" not in order_book_source
    assert "NO BOOK DATA" in order_book_source
    assert "SHOCK PROB" not in liquidity_source
    assert "CURRENT STRESS" in liquidity_source
    assert "VISIBLE LIQUIDITY" in large_order_source
    assert "IMPACT PREDICTION" not in large_order_source
    assert "SHARPE" not in agent_source
    assert "STATE" in agent_source
    assert "RL POLICY" not in dashboard_source
    assert "against the live book" not in dashboard_source


def test_dashboard_identifies_nasdaq_sim_source():
    dashboard_source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    websocket_source = WEBSOCKET.read_text(encoding="utf-8")
    types_source = MARKET_TYPES.read_text(encoding="utf-8")

    assert "SIM: NASDAQ" in dashboard_source
    assert "market: data.market ?? 'NASDAQ'" in websocket_source
    assert "market?: string;" in types_source


def test_dashboard_places_research_controls_in_an_advanced_section():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "ADVANCED SIM CONTROLS" in source
    assert "<details" in source


def test_dashboard_uses_dollar_formatting_for_nasdaq_sim():
    dashboard_source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    chart_source = (ROOT / "frontend" / "components" / "PriceChart.tsx").read_text(encoding="utf-8")
    book_source = (ROOT / "frontend" / "components" / "OrderBookHeatmap.tsx").read_text(encoding="utf-8")

    assert "marketData.market === 'NASDAQ'" in dashboard_source
    assert "marketData?.market === 'NASDAQ'" in chart_source
    assert "marketData?.market === 'NASDAQ'" in book_source
