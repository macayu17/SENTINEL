'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Play, SlidersHorizontal, Square } from 'lucide-react';
import {
  api,
  type LatencyMode,
  type SandboxPreset,
} from '@/lib/api-client';
import { useMarketStore } from '@/store/market-store';

type SandboxEngine = 'sentinel' | 'abides';
type CommandState = 'idle' | 'loading' | 'success' | 'error';

const AGENT_ORDER = [
  'MarketMaker',
  'HFT',
  'Institutional',
  'Retail',
  'Informed',
  'Noise',
  'Momentum',
  'MeanReversion',
  'Spoofing',
  'Sentiment',
];

const FALLBACK_PRESETS: Record<string, SandboxPreset> = {
  minimal: {
    name: 'Minimal',
    description: '10 agents - fast iteration',
    icon: '',
    agents: { MarketMaker: 1, HFT: 2, Noise: 3, Retail: 2, Informed: 1, Sentiment: 1 },
    oracle: false,
    latency: 'deterministic',
  },
  balanced: {
    name: 'Balanced',
    description: '40 agents - realistic mix',
    icon: '',
    agents: {
      MarketMaker: 3,
      HFT: 2,
      Institutional: 2,
      Retail: 10,
      Informed: 3,
      Noise: 10,
      Momentum: 2,
      MeanReversion: 2,
      Spoofing: 1,
      Sentiment: 5,
    },
    oracle: false,
    latency: 'deterministic',
  },
};

const DEFAULT_AGENT_COUNTS = FALLBACK_PRESETS.balanced.agents;

function toFiniteNumber(value: number, fallback: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function commandText(
  state: CommandState,
  connected: boolean,
  running: boolean,
  sandboxApiAvailable: boolean,
): string {
  if (state === 'loading') return 'COMMAND PENDING';
  if (state === 'error') return 'COMMAND REJECTED';
  if (!sandboxApiAvailable) return 'LEGACY API';
  if (running) return 'SANDBOX RUNNING';
  return connected ? 'READY' : 'BACKEND OFFLINE';
}

function NumericField({
  label,
  value,
  min,
  max,
  step = 1,
  disabled = false,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block min-w-0">
      <span className="block truncate text-[10px] tracking-[0.14em] text-gray-500">{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
        className="mt-1 h-8 w-full border border-gray-800 bg-black px-2 font-mono text-xs text-gray-100 outline-none transition-colors focus:border-[#00bfff] disabled:text-gray-600"
      />
    </label>
  );
}

function ToggleButton({
  active,
  disabled = false,
  children,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`border px-3 py-2 text-left text-[11px] font-bold tracking-[0.12em] transition-colors ${
        active
          ? 'border-[#00ff41] bg-[#00ff41]/10 text-[#00ff41]'
          : 'border-gray-800 bg-black/40 text-gray-500 hover:border-gray-600 hover:text-gray-300'
      } disabled:cursor-not-allowed disabled:border-gray-900 disabled:bg-black/30 disabled:text-gray-700`}
    >
      {children}
    </button>
  );
}

export default function SandboxControlPanel() {
  const connected = useMarketStore((state) => state.connected);
  const simulationRunning = useMarketStore((state) => state.simulationRunning);
  const resetSimulationData = useMarketStore((state) => state.resetSimulationData);
  const setSimulationRunning = useMarketStore((state) => state.setSimulationRunning);
  const setSimulationMode = useMarketStore((state) => state.setSimulationMode);

  const [engine, setEngine] = useState<SandboxEngine>('sentinel');
  const [activeEngine, setActiveEngine] = useState<SandboxEngine>('sentinel');
  const [presets, setPresets] = useState<Record<string, SandboxPreset>>(FALLBACK_PRESETS);
  const [preset, setPreset] = useState('balanced');
  const [sandboxApiAvailable, setSandboxApiAvailable] = useState(true);
  const [abidesAvailable, setAbidesAvailable] = useState(true);
  const [customAgentsEnabled, setCustomAgentsEnabled] = useState(false);
  const [agentCounts, setAgentCounts] = useState<Record<string, number>>(DEFAULT_AGENT_COUNTS);
  const [initialPrice, setInitialPrice] = useState(100);
  const [speed, setSpeed] = useState(1);
  const [latencyMode, setLatencyMode] = useState<LatencyMode>('deterministic');
  const [oracleEnabled, setOracleEnabled] = useState(false);
  const [oracleKappa, setOracleKappa] = useState(0.05);
  const [oracleSigma, setOracleSigma] = useState(0.02);
  const [marketMakers, setMarketMakers] = useState(1);
  const [noiseAgents, setNoiseAgents] = useState(2);
  const [informedAgents, setInformedAgents] = useState(1);
  const [commandState, setCommandState] = useState<CommandState>('idle');
  const [commandMessage, setCommandMessage] = useState('Preset controls synced with backend.');

  const selectedPreset = presets[preset] ?? presets.balanced ?? FALLBACK_PRESETS.balanced;
  const selectedAgentCounts = customAgentsEnabled ? agentCounts : selectedPreset.agents;
  const totalAgents = useMemo(
    () => Object.values(selectedAgentCounts).reduce((sum, count) => sum + Math.max(0, count), 0),
    [selectedAgentCounts],
  );
  const abidesAgentTotal = marketMakers + noiseAgents + informedAgents;

  useEffect(() => {
    let cancelled = false;

    const loadSandboxMetadata = async () => {
      try {
        const [nextPresets, capabilities] = await Promise.all([
          api.getSandboxPresets(),
          api.getSandboxCapabilities(),
        ]);
        if (cancelled) return;

        setSandboxApiAvailable(true);
        setPresets(nextPresets);
        setAbidesAvailable(capabilities.abides);
        const backendPreset = nextPresets[preset] ?? nextPresets.balanced;
        if (backendPreset) {
          setAgentCounts(backendPreset.agents);
          setOracleEnabled(backendPreset.oracle);
          setLatencyMode(backendPreset.latency);
        }
      } catch {
        if (cancelled) return;
        setSandboxApiAvailable(false);
        setAbidesAvailable(false);
        setEngine('sentinel');
        setCommandState('idle');
        setCommandMessage('Legacy backend detected. Launch starts the default simulation until sandbox endpoints deploy.');
      }
    };

    void loadSandboxMetadata();

    return () => {
      cancelled = true;
    };
  }, [preset]);

  const updatePreset = (nextPreset: string) => {
    const next = presets[nextPreset];
    setPreset(nextPreset);
    if (next) {
      setAgentCounts(next.agents);
      setOracleEnabled(next.oracle);
      setLatencyMode(next.latency);
    }
  };

  const updateAgentCount = (agentType: string, value: number) => {
    setAgentCounts((current) => ({
      ...current,
      [agentType]: toFiniteNumber(value, 0, 0, 300),
    }));
  };

  const launchSandbox = async () => {
    setCommandState('loading');
    setCommandMessage('Arming configured sandbox...');

    const safeInitialPrice = toFiniteNumber(initialPrice, 100, 0.01, 1000000);
    const safeSpeed = toFiniteNumber(speed, 1, 0.1, 20);

    try {
      resetSimulationData();
      await api.setSimulationMode('SANDBOX');

      if (!sandboxApiAvailable) {
        const response = await api.startSimulation();
        setActiveEngine('sentinel');
        setSimulationMode('SANDBOX');
        setSimulationRunning(true);
        setCommandState('success');
        setCommandMessage(`Default simulation online / ${response.agents} agents.`);
        return;
      }

      if (engine === 'abides') {
        if (!abidesAvailable) {
          throw new Error('ABIDES endpoints are not deployed on this backend.');
        }
        const response = await api.createAbidesSandbox({
          initial_price: safeInitialPrice,
          oracle_enabled: oracleEnabled,
          oracle_kappa: toFiniteNumber(oracleKappa, 0.05, 0, 1),
          oracle_sigma: toFiniteNumber(oracleSigma, 0.02, 0, 1),
          latency_mode: latencyMode,
          speed: safeSpeed,
          market_makers: toFiniteNumber(marketMakers, 1, 0, 50),
          noise_agents: toFiniteNumber(noiseAgents, 2, 0, 300),
          informed_agents: toFiniteNumber(informedAgents, 1, 0, 100),
        });
        setCommandMessage(`ABIDES online / ${response.agents} agents / speed ${response.speed}x`);
      } else {
        const response = await api.createSandbox({
          preset,
          initial_price: safeInitialPrice,
          oracle_enabled: oracleEnabled,
          oracle_kappa: toFiniteNumber(oracleKappa, 0.05, 0, 1),
          oracle_sigma: toFiniteNumber(oracleSigma, 0.02, 0, 1),
          latency_mode: latencyMode,
          speed: safeSpeed,
          custom_agents: customAgentsEnabled ? selectedAgentCounts : null,
        });
        setCommandMessage(`${response.preset.toUpperCase()} online / ${response.agents} agents / speed ${response.speed}x`);
      }

      setActiveEngine(engine);
      setSimulationMode('SANDBOX');
      setSimulationRunning(true);
      setCommandState('success');
    } catch (error) {
      setCommandState('error');
      setSimulationRunning(false);
      setCommandMessage(error instanceof Error ? error.message : 'Sandbox launch failed.');
    }
  };

  const stopSandbox = async () => {
    setCommandState('loading');
    setCommandMessage('Stopping active simulation...');

    try {
      await api.stopSimulation();
      resetSimulationData();
      setSimulationRunning(false);
      setCommandState('success');
      setCommandMessage('Simulation stopped.');
    } catch (error) {
      setCommandState('error');
      setCommandMessage(error instanceof Error ? error.message : 'Stop command failed.');
    }
  };

  const applySpeed = async () => {
    setCommandState('loading');
    setCommandMessage('Updating playback clock...');

    try {
      const response =
        activeEngine === 'abides'
          ? await api.setAbidesSpeed(toFiniteNumber(speed, 1, 0.1, 20))
          : await api.setSandboxSpeed(toFiniteNumber(speed, 1, 0.1, 20));

      if ('error' in response) {
        throw new Error(response.error);
      }

      setCommandState('success');
      setCommandMessage(`Speed set to ${response.speed}x.`);
    } catch (error) {
      setCommandState('error');
      setCommandMessage(error instanceof Error ? error.message : 'Speed update failed.');
    }
  };

  return (
    <div className="terminal-panel">
      <div className="panel-header">
        <div className="flex items-center gap-3">
          <span className="panel-tag">SANDBOX CONTROL</span>
          <span className="text-[10px] tracking-[0.14em] text-[#00bfff]">
            {engine === 'abides' ? 'ABIDES ENGINE' : 'SENTINEL ENGINE'}
          </span>
        </div>
        <span
          className={`text-[10px] font-bold tracking-[0.14em] ${
            commandState === 'error'
              ? 'text-[#ff0040]'
              : simulationRunning
                ? 'text-[#00ff41]'
                : !sandboxApiAvailable
                  ? 'text-[#ffb800]'
                : 'text-gray-500'
          }`}
        >
          {commandText(commandState, connected, simulationRunning, sandboxApiAvailable)}
        </span>
      </div>

      <div className="grid gap-3 p-3 xl:grid-cols-[1fr_1fr_1.2fr]">
        <div className="space-y-3 border border-gray-900 bg-black/30 p-3">
          <div className="grid grid-cols-2 gap-2">
            <ToggleButton active={engine === 'sentinel'} onClick={() => setEngine('sentinel')}>
              SENTINEL
            </ToggleButton>
            <ToggleButton
              active={engine === 'abides'}
              disabled={!sandboxApiAvailable || !abidesAvailable}
              onClick={() => setEngine('abides')}
            >
              ABIDES
            </ToggleButton>
          </div>

          {engine === 'sentinel' ? (
            <label className="block">
              <span className="block text-[10px] tracking-[0.14em] text-gray-500">PRESET</span>
              <select
                value={preset}
                disabled={!sandboxApiAvailable}
                onChange={(event) => updatePreset(event.currentTarget.value)}
                className="mt-1 h-8 w-full border border-gray-800 bg-black px-2 font-mono text-xs text-gray-100 outline-none focus:border-[#00bfff] disabled:text-gray-600"
              >
                {Object.entries(presets).map(([key, value]) => (
                  <option key={key} value={key}>
                    {value.name} / {value.description}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="border border-gray-900 bg-black/40 p-2 text-xs text-gray-400">
              <div className="text-[10px] tracking-[0.14em] text-gray-500">CAPABILITY</div>
              <div className={abidesAvailable ? 'mt-1 text-[#00ff41]' : 'mt-1 text-[#ff0040]'}>
                {abidesAvailable ? 'ABIDES MODULE AVAILABLE' : 'ABIDES MODULE DISABLED'}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <NumericField
              label="START PX"
              value={initialPrice}
              min={0.01}
              max={1000000}
              step={0.01}
              onChange={setInitialPrice}
            />
            <NumericField
              label="SPEED"
              value={speed}
              min={0.1}
              max={20}
              step={0.1}
              onChange={setSpeed}
            />
          </div>
        </div>

        <div className="space-y-3 border border-gray-900 bg-black/30 p-3">
          <label className="block">
            <span className="block text-[10px] tracking-[0.14em] text-gray-500">LATENCY MODEL</span>
            <select
              value={latencyMode}
              onChange={(event) => setLatencyMode(event.currentTarget.value as LatencyMode)}
              className="mt-1 h-8 w-full border border-gray-800 bg-black px-2 font-mono text-xs text-gray-100 outline-none focus:border-[#00bfff]"
            >
              <option value="zero">ZERO</option>
              <option value="deterministic">DETERMINISTIC</option>
              <option value="cubic">CUBIC</option>
            </select>
          </label>

          <button
            type="button"
            onClick={() => setOracleEnabled((value) => !value)}
            className={`flex h-8 w-full items-center justify-between border px-2 text-xs font-bold tracking-[0.12em] transition-colors ${
              oracleEnabled
                ? 'border-[#ffb800] bg-[#ffb800]/10 text-[#ffb800]'
                : 'border-gray-800 bg-black text-gray-500'
            }`}
          >
            <span>ORACLE</span>
            <span>{oracleEnabled ? 'ENABLED' : 'DISABLED'}</span>
          </button>

          <div className="grid grid-cols-2 gap-2">
            <NumericField
              label="KAPPA"
              value={oracleKappa}
              min={0}
              max={1}
              step={0.01}
              onChange={setOracleKappa}
            />
            <NumericField
              label="SIGMA"
              value={oracleSigma}
              min={0}
              max={1}
              step={0.01}
              onChange={setOracleSigma}
            />
          </div>
        </div>

        <div className="border border-gray-900 bg-black/30 p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="text-[10px] tracking-[0.14em] text-gray-500">
              {engine === 'sentinel' ? 'AGENT MIX' : 'ABIDES AGENTS'}
            </span>
            {engine === 'sentinel' ? (
              <button
                type="button"
                onClick={() => setCustomAgentsEnabled((value) => !value)}
                className={`border px-2 py-1 text-[10px] font-bold tracking-[0.12em] ${
                  customAgentsEnabled
                    ? 'border-[#00bfff] text-[#00bfff]'
                    : 'border-gray-800 text-gray-500'
                }`}
              >
                {customAgentsEnabled ? 'CUSTOM' : 'PRESET'} / {totalAgents}
              </button>
            ) : (
              <span className="text-[10px] tracking-[0.14em] text-[#00bfff]">{abidesAgentTotal} AGENTS</span>
            )}
          </div>

          {engine === 'sentinel' ? (
            <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
              {AGENT_ORDER.map((agentType) => (
                <NumericField
                  key={agentType}
                  label={agentType.toUpperCase()}
                  value={selectedAgentCounts[agentType] ?? 0}
                  min={0}
                  max={300}
                  disabled={!customAgentsEnabled}
                  onChange={(value) => updateAgentCount(agentType, value)}
                />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              <NumericField
                label="MAKERS"
                value={marketMakers}
                min={0}
                max={50}
                onChange={setMarketMakers}
              />
              <NumericField
                label="NOISE"
                value={noiseAgents}
                min={0}
                max={300}
                onChange={setNoiseAgents}
              />
              <NumericField
                label="INFORMED"
                value={informedAgents}
                min={0}
                max={100}
                onChange={setInformedAgents}
              />
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3 border-t border-gray-900 px-3 py-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 truncate text-xs text-gray-500">
          <span className={commandState === 'error' ? 'text-[#ff0040]' : 'text-gray-300'}>
            {commandMessage}
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={launchSandbox}
            disabled={
              commandState === 'loading'
              || (engine === 'abides' && (!sandboxApiAvailable || !abidesAvailable))
            }
            className="inline-flex items-center gap-2 border border-[#00ff41] bg-[#00ff41]/10 px-3 py-1.5 text-xs font-bold tracking-[0.12em] text-[#00ff41] disabled:cursor-not-allowed disabled:border-gray-800 disabled:text-gray-600"
          >
            <Play size={13} />
            LAUNCH
          </button>
          <button
            type="button"
            onClick={applySpeed}
            disabled={commandState === 'loading' || !simulationRunning || !sandboxApiAvailable}
            className="inline-flex items-center gap-2 border border-[#00bfff] bg-[#00bfff]/10 px-3 py-1.5 text-xs font-bold tracking-[0.12em] text-[#00bfff] disabled:cursor-not-allowed disabled:border-gray-800 disabled:text-gray-600"
          >
            <SlidersHorizontal size={13} />
            APPLY SPEED
          </button>
          <button
            type="button"
            onClick={stopSandbox}
            disabled={commandState === 'loading' || !simulationRunning}
            className="inline-flex items-center gap-2 border border-[#ff0040] bg-[#ff0040]/10 px-3 py-1.5 text-xs font-bold tracking-[0.12em] text-[#ff0040] disabled:cursor-not-allowed disabled:border-gray-800 disabled:text-gray-600"
          >
            <Square size={12} />
            STOP
          </button>
        </div>
      </div>
    </div>
  );
}
