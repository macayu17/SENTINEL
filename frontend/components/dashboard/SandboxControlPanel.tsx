'use client';

import { useEffect, useMemo, useState } from 'react';
import { Download, Play, SlidersHorizontal, Square } from 'lucide-react';
import { api, type LatencyMode, type SandboxPreset, type SandboxScenario } from '@/lib/api-client';
import { useMarketStore } from '@/store/market-store';

type CommandState = 'idle' | 'loading' | 'success' | 'error';

const FALLBACK_PRESETS: Record<string, SandboxPreset> = {
  balanced: {
    name: 'Balanced',
    description: '40 agents - realistic mix',
    icon: '',
    agents: {
      MarketMaker: 3, HFT: 2, Institutional: 2, Retail: 10, Informed: 3,
      Noise: 10, LiquidityTrader: 1, Momentum: 2, MeanReversion: 2,
      Spoofing: 0, Sentiment: 5,
    },
    oracle: false,
    latency: 'deterministic',
  },
};

const FALLBACK_SCENARIOS: SandboxScenario[] = [{
  name: 'normal',
  label: 'Normal Session',
  description: 'Balanced continuous double-auction session.',
  seed_depth_multiplier: 1,
  liquidity_floor_multiplier: 1,
  spread_multiplier: 1,
  oracle_sigma_multiplier: 1,
  order_ttl_seconds: 20,
  volatility_multiplier: 1,
  enable_spoofing: false,
  institutional_multiplier: 1,
}];

const FIELD_CLASS = 'mt-1 h-10 w-full border border-gray-800 bg-black px-2 font-mono text-xs text-gray-100 outline-none focus:border-[#00bfff]';

function safeNumber(value: number, fallback: number, min: number, max: number) {
  return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
}

function commandText(state: CommandState, connected: boolean, running: boolean, apiAvailable: boolean) {
  if (state === 'loading') return 'COMMAND PENDING';
  if (state === 'error') return 'COMMAND REJECTED';
  if (!apiAvailable) return 'BACKEND API UNAVAILABLE';
  if (running) return 'SANDBOX RUNNING';
  return connected ? 'READY' : 'BACKEND OFFLINE';
}

function NumberField({ label, value, min, max, step = 1, onChange }: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block min-w-0">
      <span className="block truncate text-[10px] tracking-[0.14em] text-gray-500">{label}</span>
      <input type="number" min={min} max={max} step={step} value={value}
        onChange={(event) => onChange(Number(event.currentTarget.value))} className={FIELD_CLASS} />
    </label>
  );
}

export default function SandboxControlPanel() {
  const connected = useMarketStore((state) => state.connected);
  const simulationRunning = useMarketStore((state) => state.simulationRunning);
  const resetSimulationData = useMarketStore((state) => state.resetSimulationData);
  const setSimulationRunning = useMarketStore((state) => state.setSimulationRunning);
  const [presets, setPresets] = useState(FALLBACK_PRESETS);
  const [preset, setPreset] = useState('balanced');
  const [scenarios, setScenarios] = useState(FALLBACK_SCENARIOS);
  const [scenario, setScenario] = useState('normal');
  const [initialPrice, setInitialPrice] = useState(100);
  const [speed, setSpeed] = useState(1);
  const [latencyMode, setLatencyMode] = useState<LatencyMode>('deterministic');
  const [oracleEnabled, setOracleEnabled] = useState(false);
  const [apiAvailable, setApiAvailable] = useState(true);
  const [commandState, setCommandState] = useState<CommandState>('idle');
  const [message, setMessage] = useState('Loading simulator controls...');

  const selectedPreset = presets[preset] ?? FALLBACK_PRESETS.balanced;
  const totalAgents = useMemo(
    () => Object.values(selectedPreset.agents).reduce((sum, count) => sum + Math.max(0, count), 0),
    [selectedPreset.agents],
  );

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getSandboxPresets(), api.getSandboxScenarios()])
      .then(([nextPresets, nextScenarios]) => {
        if (cancelled) return;
        const nextPreset = nextPresets.balanced ? 'balanced' : Object.keys(nextPresets)[0];
        setPresets(nextPresets);
        setPreset(nextPreset);
        setLatencyMode(nextPresets[nextPreset].latency);
        setOracleEnabled(nextPresets[nextPreset].oracle);
        setScenarios(nextScenarios.scenarios);
        setApiAvailable(true);
        setMessage('Preset controls synced with backend.');
      })
      .catch(() => {
        if (cancelled) return;
        setApiAvailable(false);
        setMessage('Sandbox metadata unavailable.');
      });
    return () => { cancelled = true; };
  }, []);

  const updatePreset = (value: string) => {
    const next = presets[value];
    setPreset(value);
    if (!next) return;
    setLatencyMode(next.latency);
    setOracleEnabled(next.oracle);
  };

  const launch = async () => {
    setCommandState('loading');
    setMessage('Starting configured sandbox...');
    const wasRunning = simulationRunning;
    try {
      const response = await api.createSandbox({
        preset,
        initial_price: safeNumber(initialPrice, 100, 0.01, 1_000_000),
        oracle_enabled: oracleEnabled,
        latency_mode: latencyMode,
        speed: safeNumber(speed, 1, 0.1, 20),
        scenario,
      });
      resetSimulationData();
      setSimulationRunning(true);
      setCommandState('success');
      setMessage(`${response.preset.toUpperCase()} online / ${response.agents} agents / ${response.scenario}`);
    } catch (error) {
      setSimulationRunning(wasRunning);
      setCommandState('error');
      setMessage(error instanceof Error ? error.message : 'Sandbox launch failed.');
    }
  };

  const stop = async () => {
    setCommandState('loading');
    try {
      await api.stopSimulation();
      resetSimulationData();
      setSimulationRunning(false);
      setCommandState('success');
      setMessage('Simulation stopped.');
    } catch (error) {
      setCommandState('error');
      setMessage(error instanceof Error ? error.message : 'Stop failed.');
    }
  };

  const applySpeed = async () => {
    setCommandState('loading');
    try {
      const response = await api.setSandboxSpeed(safeNumber(speed, 1, 0.1, 20));
      if ('error' in response) throw new Error(response.error);
      setCommandState('success');
      setMessage(`Speed set to ${response.speed}x.`);
    } catch (error) {
      setCommandState('error');
      setMessage(error instanceof Error ? error.message : 'Speed update failed.');
    }
  };

  const exportRun = async () => {
    try {
      const blob = new Blob([JSON.stringify(await api.exportSimulation(), null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `sentinel-run-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage('Run snapshot exported.');
    } catch (error) {
      setCommandState('error');
      setMessage(error instanceof Error ? error.message : 'Export failed.');
    }
  };

  const busy = commandState === 'loading';
  return (
    <div className="terminal-panel">
      <div className="panel-header">
        <div className="flex items-center gap-3"><span className="panel-tag">SIM MODE</span><span className="text-[10px] tracking-[0.14em] text-[#00bfff]">SENTINEL ENGINE</span></div>
        <span className={`text-[10px] font-bold tracking-[0.14em] ${commandState === 'error' ? 'text-[#ff0040]' : simulationRunning ? 'text-[#00ff41]' : 'text-gray-500'}`}>
          {commandText(commandState, connected, simulationRunning, apiAvailable)}
        </span>
      </div>

      <div className="grid gap-3 p-3 xl:grid-cols-[1fr_2.2fr]">
        <section className="space-y-3 border border-gray-900 bg-black/30 p-3">
          <label className="block"><span className="text-[10px] tracking-[0.14em] text-gray-500">PRESET</span>
            <select value={preset} onChange={(event) => updatePreset(event.currentTarget.value)} className={FIELD_CLASS}>
              {Object.entries(presets).map(([key, value]) => <option key={key} value={key}>{value.name} / {value.description}</option>)}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <NumberField label="START PRICE" value={initialPrice} min={0.01} max={1_000_000} step={0.01} onChange={setInitialPrice} />
            <NumberField label="SPEED" value={speed} min={0.1} max={20} step={0.1} onChange={setSpeed} />
          </div>
          <label className="block"><span className="text-[10px] tracking-[0.14em] text-gray-500">SCENARIO</span>
            <select value={scenario} onChange={(event) => setScenario(event.currentTarget.value)} className={FIELD_CLASS}>
              {scenarios.map((item) => <option key={item.name} value={item.name}>{item.label} / {item.name}</option>)}
            </select>
          </label>
        </section>

        <details open className="self-start border border-gray-900 bg-black/30 p-3">
          <summary className="cursor-pointer list-none text-[10px] font-bold tracking-[0.16em] text-gray-500">ADVANCED SIM CONTROLS</summary>
          <div className="mt-3 grid gap-4 xl:grid-cols-[0.7fr_1.3fr]">
            <section className="space-y-3">
              <label className="block"><span className="text-[10px] tracking-[0.14em] text-gray-500">LATENCY MODEL</span>
                <select value={latencyMode} onChange={(event) => setLatencyMode(event.currentTarget.value as LatencyMode)} className={FIELD_CLASS}>
                  <option value="zero">ZERO</option><option value="deterministic">DETERMINISTIC</option><option value="cubic">CUBIC</option>
                </select>
              </label>
              <button type="button" onClick={() => setOracleEnabled((value) => !value)} className={`w-full border px-3 py-2 text-left text-[11px] font-bold tracking-[0.12em] ${oracleEnabled ? 'border-[#00ff41] text-[#00ff41]' : 'border-gray-800 text-gray-500'}`}>
                INFORMED ACCESS {oracleEnabled ? 'ON' : 'OFF'}
              </button>
            </section>
            <section className="border border-gray-900 bg-black/20 p-3">
              <div className="text-[10px] tracking-[0.14em] text-gray-500">PRESET POPULATION</div>
              <div className="mt-2 text-sm font-semibold text-gray-200">{totalAgents} agents</div>
              <div className="mt-1 text-xs text-gray-500">{selectedPreset.description}</div>
            </section>
          </div>
        </details>
      </div>

      <div className="flex flex-col gap-3 border-t border-gray-900 px-3 py-2 lg:flex-row lg:items-center lg:justify-between">
        <span className={`text-xs ${commandState === 'error' ? 'text-[#ff0040]' : 'text-gray-400'}`}>{message}</span>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={launch} disabled={busy || !apiAvailable} className="inline-flex items-center gap-2 border border-[#00ff41] px-3 py-1.5 text-xs font-bold text-[#00ff41] disabled:border-gray-800 disabled:text-gray-600"><Play size={13} />LAUNCH</button>
          <button type="button" onClick={applySpeed} disabled={busy || !simulationRunning} className="inline-flex items-center gap-2 border border-[#00bfff] px-3 py-1.5 text-xs font-bold text-[#00bfff] disabled:border-gray-800 disabled:text-gray-600"><SlidersHorizontal size={13} />APPLY SPEED</button>
          <button type="button" onClick={exportRun} disabled={busy || !simulationRunning} className="inline-flex items-center gap-2 border border-[#ffb800] px-3 py-1.5 text-xs font-bold text-[#ffb800] disabled:border-gray-800 disabled:text-gray-600"><Download size={13} />EXPORT</button>
          <button type="button" onClick={stop} disabled={busy || !simulationRunning} className="inline-flex items-center gap-2 border border-[#ff0040] px-3 py-1.5 text-xs font-bold text-[#ff0040] disabled:border-gray-800 disabled:text-gray-600"><Square size={12} />STOP</button>
        </div>
      </div>
    </div>
  );
}
