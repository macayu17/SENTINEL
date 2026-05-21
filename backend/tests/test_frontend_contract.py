from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SANDBOX_PANEL = ROOT / "frontend" / "components" / "dashboard" / "SandboxControlPanel.tsx"


def test_live_shadow_provider_launches_do_not_pre_switch_backend_mode():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "api.setSimulationMode('LIVE_SHADOW')" not in source


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


def test_upstox_panel_exposes_search_and_live_ltp_mode():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "api.searchUpstoxInstruments" in source
    assert "upstoxFeedMode" in source
    assert "UPSTOX LIVE LTP" in source
    assert "api.startUpstoxLive" in source


def test_upstox_panel_uses_selectable_results_and_date_inputs():
    source = SANDBOX_PANEL.read_text(encoding="utf-8")

    assert "findBestUpstoxMatch" in source
    assert 'label="MATCHES"' in source
    assert "DateField" in source
    assert 'type="date"' in source
