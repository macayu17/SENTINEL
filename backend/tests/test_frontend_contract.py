from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SANDBOX_PANEL = ROOT / "frontend" / "components" / "dashboard" / "SandboxControlPanel.tsx"
DASHBOARD_PAGE = ROOT / "frontend" / "app" / "dashboard" / "page.tsx"
API_CLIENT = ROOT / "frontend" / "lib" / "api-client.ts"
MARKET_STORE = ROOT / "frontend" / "store" / "market-store.ts"
MARKET_TYPES = ROOT / "frontend" / "types" / "market.ts"
WEBSOCKET = ROOT / "frontend" / "lib" / "websocket.ts"
MOCK_SIMULATION = ROOT / "frontend" / "lib" / "mock-simulation.ts"


def test_live_shadow_provider_launches_do_not_pre_switch_backend_mode():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "api.setSimulationMode('LIVE_SHADOW')" not in source


def test_dashboard_header_mode_indicator_is_not_a_generic_live_shadow_toggle():
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")

    assert "handleModeToggle" not in source
    assert "api.setSimulationMode(nextMode)" not in source


def test_frontend_exposes_simulation_export_endpoint():
    source = API_CLIENT.read_text(encoding="utf-8")

    assert "exportSimulation" in source
    assert "/api/simulation/export" in source


def test_api_client_cannot_request_generic_live_shadow_mode():
    source = API_CLIENT.read_text(encoding="utf-8")

    assert "async setSimulationMode(mode: 'SANDBOX')" in source
    assert "async setSimulationMode(mode: SimulationMode)" not in source


def test_dashboard_header_does_not_bypass_sandbox_control_panel():
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")

    assert "handleStartStop" not in source
    assert "api.startSimulation()" not in source
    assert "api.stopSimulation()" not in source


def test_reset_simulation_data_restores_sandbox_mode():
    source = MARKET_STORE.read_text(encoding="utf-8")

    reset_start = source.rindex("resetSimulationData:")
    reset_end = source.index("setSimulationRunning:", reset_start)
    reset_block = source[reset_start:reset_end]
    assert "simulationMode: 'SANDBOX'" in reset_block


def test_sandbox_panel_has_export_command_for_running_runs():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "exportSimulation" in source
    assert "EXPORT" in source
    assert "URL.createObjectURL" in source


def test_failed_provider_launch_preserves_existing_running_state():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "const previousRunning = simulationRunning" in source
    assert "setSimulationRunning(previousRunning)" in source


def test_replay_running_label_uses_active_engine_not_selected_tab():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "activeEngine: SandboxEngine" in source
    assert "activeEngine === 'groww' && running" in source
    assert "activeEngine === 'upstox' && running" in source
    assert re.search(
        r"commandText\(\s*commandState,\s*connected,\s*simulationRunning,\s*"
        r"sandboxApiAvailable,\s*engine,\s*activeEngine,",
        source,
    )


def test_upstox_panel_exposes_search_and_live_depth_mode():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "api.searchUpstoxInstruments" in source
    assert "upstoxFeedMode" in source
    assert "UPSTOX LIVE DEPTH" in source
    assert "api.startUpstoxLive" in source


def test_groww_panel_exposes_historical_and_live_depth_modes():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "growwFeedMode" in source
    assert "GROWW LIVE DEPTH" in source
    assert "api.startGrowwLive" in source


def test_upstox_panel_uses_selectable_results_and_date_inputs():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "findBestUpstoxMatch" in source
    assert 'label="MATCHES"' in source
    assert "DateField" in source
    assert 'type="date"' in source


def test_sandbox_panel_exposes_scenario_selection():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "api.getSandboxScenarios" in source
    assert "scenario" in source
    assert "SCENARIO" in source
    assert "spoofing_stress" in source


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


def test_dashboard_trace_panels_prefer_backend_market_update_fields():
    source = MOCK_SIMULATION.read_text(encoding="utf-8")

    assert "mapBackendEvents" in source
    assert "buildBackendAgentActivity" in source
    assert "marketData.events" in source
    assert "marketData.order_flow" in source
    assert "marketData.recent_orders" in source
    assert "setTradeFlow((prev) => mergeBackendTradeFlow" in source
    assert "setEvents(mapBackendEvents(marketData.events))" in source
