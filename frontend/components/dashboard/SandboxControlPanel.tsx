'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Play, Search, SlidersHorizontal, Square } from 'lucide-react';
import {
  api,
  type LatencyMode,
  type SandboxPreset,
  type UpstoxInstrumentResult,
} from '@/lib/api-client';
import { useMarketStore } from '@/store/market-store';

type SandboxEngine = 'sentinel' | 'abides' | 'groww' | 'upstox';
type UpstoxFeedMode = 'historical' | 'live';
type CommandState = 'idle' | 'loading' | 'success' | 'error';
type AbidesCapability = 'available' | 'disabled' | 'unverified';

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
const DEFAULT_GROWW_REPLAY = {
  groww_symbol: 'RELIANCE',
  exchange: 'NSE',
  segment: 'CASH',
  start_time: '2025-09-24 09:15:00',
  end_time: '2025-09-24 15:30:00',
  candle_interval: 'MIN_30',
};
const DEFAULT_UPSTOX_REPLAY = {
  instrument_key: 'NSE_EQ|INE002A01018',
  unit: 'minutes',
  interval: '30',
  from_date: '2025-01-01',
  to_date: '2025-01-01',
};

function toFiniteNumber(value: number, fallback: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function commandText(
  state: CommandState,
  connected: boolean,
  running: boolean,
  sandboxApiAvailable: boolean,
  engine: SandboxEngine,
  activeEngine: SandboxEngine,
  abidesCapability: AbidesCapability,
  liveDataProvider?: string | null,
  liveDataSource?: string | null,
): string {
  const growwReplayRunning = (activeEngine === 'groww' && running) || (liveDataProvider === 'groww' && running);
  const upstoxReplayRunning = (activeEngine === 'upstox' && running) || (liveDataProvider === 'upstox' && running);

  if (state === 'loading') return 'COMMAND PENDING';
  if (state === 'error') return 'COMMAND REJECTED';
  if (engine === 'abides' && abidesCapability !== 'disabled' && !sandboxApiAvailable) return 'ABIDES PROBE';
  if (engine === 'groww' && growwReplayRunning) return 'GROWW REPLAY RUNNING';
  if (engine === 'groww') return connected ? 'GROWW READY' : 'BACKEND OFFLINE';
  if (engine === 'upstox' && upstoxReplayRunning) {
    return liveDataSource === 'live_ltp' ? 'UPSTOX LIVE RUNNING' : 'UPSTOX REPLAY RUNNING';
  }
  if (engine === 'upstox') return connected ? 'UPSTOX READY' : 'BACKEND OFFLINE';
  if (!sandboxApiAvailable) return 'LEGACY API';
  if (running) return 'SANDBOX RUNNING';
  return connected ? 'READY' : 'BACKEND OFFLINE';
}

function abidesCapabilityText(capability: AbidesCapability): string {
  if (capability === 'available') return 'ABIDES MODULE AVAILABLE';
  if (capability === 'disabled') return 'ABIDES MODULE DISABLED';
  return 'ABIDES MODULE UNVERIFIED';
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

function TextField({
  label,
  value,
  disabled = false,
  onChange,
}: {
  label: string;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block min-w-0">
      <span className="block truncate text-[10px] tracking-[0.14em] text-gray-500">{label}</span>
      <input
        type="text"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.currentTarget.value)}
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
  const marketData = useMarketStore((state) => state.marketData);

  const [engine, setEngine] = useState<SandboxEngine>('sentinel');
  const [activeEngine, setActiveEngine] = useState<SandboxEngine>('sentinel');
  const [presets, setPresets] = useState<Record<string, SandboxPreset>>(FALLBACK_PRESETS);
  const [preset, setPreset] = useState('balanced');
  const [sandboxApiAvailable, setSandboxApiAvailable] = useState(true);
  const [abidesCapability, setAbidesCapability] = useState<AbidesCapability>('unverified');
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
  const [growwSymbol, setGrowwSymbol] = useState(DEFAULT_GROWW_REPLAY.groww_symbol);
  const [growwExchange, setGrowwExchange] = useState(DEFAULT_GROWW_REPLAY.exchange);
  const [growwSegment, setGrowwSegment] = useState(DEFAULT_GROWW_REPLAY.segment);
  const [growwStartTime, setGrowwStartTime] = useState(DEFAULT_GROWW_REPLAY.start_time);
  const [growwEndTime, setGrowwEndTime] = useState(DEFAULT_GROWW_REPLAY.end_time);
  const [growwInterval, setGrowwInterval] = useState(DEFAULT_GROWW_REPLAY.candle_interval);
  const [upstoxInstrumentKey, setUpstoxInstrumentKey] = useState(DEFAULT_UPSTOX_REPLAY.instrument_key);
  const [upstoxUnit, setUpstoxUnit] = useState(DEFAULT_UPSTOX_REPLAY.unit);
  const [upstoxInterval, setUpstoxInterval] = useState(DEFAULT_UPSTOX_REPLAY.interval);
  const [upstoxFromDate, setUpstoxFromDate] = useState(DEFAULT_UPSTOX_REPLAY.from_date);
  const [upstoxToDate, setUpstoxToDate] = useState(DEFAULT_UPSTOX_REPLAY.to_date);
  const [upstoxFeedMode, setUpstoxFeedMode] = useState<UpstoxFeedMode>('historical');
  const [upstoxSearchQuery, setUpstoxSearchQuery] = useState('RELIANCE');
  const [upstoxSearchResults, setUpstoxSearchResults] = useState<UpstoxInstrumentResult[]>([]);
  const [upstoxPollInterval, setUpstoxPollInterval] = useState(5);
  const [commandState, setCommandState] = useState<CommandState>('idle');
  const [commandMessage, setCommandMessage] = useState('Preset controls synced with backend.');

  const selectedPreset = presets[preset] ?? presets.balanced ?? FALLBACK_PRESETS.balanced;
  const abidesAvailable = abidesCapability !== 'disabled';
  const selectedAgentCounts = customAgentsEnabled ? agentCounts : selectedPreset.agents;
  const totalAgents = useMemo(
    () => Object.values(selectedAgentCounts).reduce((sum, count) => sum + Math.max(0, count), 0),
    [selectedAgentCounts],
  );
  const abidesAgentTotal = marketMakers + noiseAgents + informedAgents;
  const growwSource = marketData?.data_source?.provider === 'groww' ? marketData.data_source : null;
  const upstoxSource = marketData?.data_source?.provider === 'upstox' ? marketData.data_source : null;
  const growwStatus = growwSource?.status ?? (engine === 'groww' && !connected ? 'disconnected' : 'idle');
  const upstoxStatus = upstoxSource?.status ?? (engine === 'upstox' && !connected ? 'disconnected' : 'idle');
  const upstoxLiveSelected = upstoxFeedMode === 'live' || upstoxSource?.source === 'live_ltp';
  const activeLiveSource = engine === 'upstox' ? upstoxSource : growwSource;
  const activeLiveStatus = engine === 'upstox' ? upstoxStatus : growwStatus;
  const activeLiveProviderLabel = engine === 'upstox'
    ? upstoxLiveSelected ? 'UPSTOX LIVE LTP' : 'UPSTOX HISTORICAL'
    : 'GROWW HISTORICAL';

  useEffect(() => {
    let cancelled = false;

    const loadSandboxMetadata = async () => {
      const [presetsResult, capabilitiesResult] = await Promise.allSettled([
        api.getSandboxPresets(),
        api.getSandboxCapabilities(),
      ]);
      if (cancelled) return;

      if (presetsResult.status === 'fulfilled') {
        const nextPresets = presetsResult.value;
        setSandboxApiAvailable(true);
        setPresets(nextPresets);
        const backendPreset = nextPresets[preset] ?? nextPresets.balanced;
        if (backendPreset) {
          setAgentCounts(backendPreset.agents);
          setOracleEnabled(backendPreset.oracle);
          setLatencyMode(backendPreset.latency);
        }
      } else {
        setSandboxApiAvailable(false);
      }

      if (capabilitiesResult.status === 'fulfilled') {
        setAbidesCapability(capabilitiesResult.value.abides ? 'available' : 'disabled');
      } else {
        setAbidesCapability('unverified');
      }

      setCommandState('idle');
      if (presetsResult.status === 'fulfilled' && capabilitiesResult.status === 'fulfilled') {
        setCommandMessage('Preset controls synced with backend.');
      } else if (capabilitiesResult.status === 'fulfilled' && capabilitiesResult.value.abides) {
        setCommandMessage('ABIDES endpoint detected. SENTINEL preset metadata is unavailable.');
      } else if (capabilitiesResult.status === 'fulfilled' && !capabilitiesResult.value.abides) {
        setCommandMessage('ABIDES module is disabled on this backend.');
      } else {
        setCommandMessage('Sandbox metadata unavailable. ABIDES launch will probe the backend directly.');
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

  const searchUpstoxInstruments = async () => {
    setCommandState('loading');
    setCommandMessage('Searching Upstox instruments...');

    try {
      const response = await api.searchUpstoxInstruments({
        query: upstoxSearchQuery.trim(),
        exchanges: 'NSE',
        segments: 'EQ',
        records: 6,
      });
      setUpstoxSearchResults(response.results);
      if (response.results[0]) {
        setUpstoxInstrumentKey(response.results[0].instrument_key);
      }
      setCommandState('success');
      setCommandMessage(`Upstox search / ${response.results.length} matches.`);
    } catch (error) {
      setCommandState('error');
      setCommandMessage(error instanceof Error ? error.message : 'Upstox instrument search failed.');
    }
  };

  const launchSandbox = async () => {
    setCommandState('loading');
    setCommandMessage('Arming configured sandbox...');

    const safeInitialPrice = toFiniteNumber(initialPrice, 100, 0.01, 1000000);
    const safeSpeed = toFiniteNumber(speed, 1, 0.1, 20);
    const previousRunning = simulationRunning;

    try {
      if (engine === 'groww') {
        const response = await api.startGrowwReplay({
          groww_symbol: growwSymbol.trim(),
          exchange: growwExchange.trim().toUpperCase(),
          segment: growwSegment.trim().toUpperCase(),
          start_time: growwStartTime.trim(),
          end_time: growwEndTime.trim(),
          candle_interval: growwInterval.trim().toUpperCase(),
          preset,
          custom_agents: customAgentsEnabled ? selectedAgentCounts : null,
          latency_mode: latencyMode,
          speed: safeSpeed,
        });
        resetSimulationData();
        setActiveEngine('groww');
        setSimulationMode('LIVE_SHADOW');
        setSimulationRunning(true);
        setCommandState('success');
        setCommandMessage(`Groww historical replay / ${response.groww_symbol} / ${response.bars} bars / ${response.speed}x`);
        return;
      }

      if (engine === 'upstox') {
        if (upstoxFeedMode === 'live') {
          const response = await api.startUpstoxLive({
            instrument_key: upstoxInstrumentKey.trim(),
            preset,
            custom_agents: customAgentsEnabled ? selectedAgentCounts : null,
            latency_mode: latencyMode,
            speed: safeSpeed,
            poll_interval_seconds: toFiniteNumber(upstoxPollInterval, 5, 1, 60),
          });
          resetSimulationData();
          setActiveEngine('upstox');
          setSimulationMode('LIVE_SHADOW');
          setSimulationRunning(true);
          setCommandState('success');
          setCommandMessage(
            `Upstox live LTP / ${response.instrument_key} / ${response.last_price.toFixed(2)} / ${response.poll_interval_seconds}s`,
          );
          return;
        }

        const response = await api.startUpstoxReplay({
          instrument_key: upstoxInstrumentKey.trim(),
          unit: upstoxUnit.trim().toLowerCase(),
          interval: upstoxInterval.trim(),
          from_date: upstoxFromDate.trim(),
          to_date: upstoxToDate.trim(),
          preset,
          custom_agents: customAgentsEnabled ? selectedAgentCounts : null,
          latency_mode: latencyMode,
          speed: safeSpeed,
        });
        resetSimulationData();
        setActiveEngine('upstox');
        setSimulationMode('LIVE_SHADOW');
        setSimulationRunning(true);
        setCommandState('success');
        setCommandMessage(`Upstox historical replay / ${response.instrument_key} / ${response.bars} bars / ${response.speed}x`);
        return;
      }

      if (engine === 'abides') {
        if (!abidesAvailable) {
          throw new Error('ABIDES endpoints are not deployed on this backend.');
        }
        resetSimulationData();
        await api.setSimulationMode('SANDBOX');
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
        setOracleEnabled(response.oracle_enabled);
        setCommandMessage(
          `ABIDES online / ${response.agents} agents / speed ${response.speed}x${
            response.oracle_auto_enabled ? ' / oracle signal' : ''
          }`,
        );
      } else if (!sandboxApiAvailable) {
        resetSimulationData();
        await api.setSimulationMode('SANDBOX');
        const response = await api.startSimulation();
        setActiveEngine('sentinel');
        setSimulationMode('SANDBOX');
        setSimulationRunning(true);
        setCommandState('success');
        setCommandMessage(`Default simulation online / ${response.agents} agents.`);
        return;
      } else {
        resetSimulationData();
        await api.setSimulationMode('SANDBOX');
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
      setSimulationRunning(previousRunning);
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
            {engine === 'abides'
              ? 'ABIDES ENGINE'
              : engine === 'groww' || engine === 'upstox'
                ? 'LIVE SHADOW DATA'
                : 'SENTINEL ENGINE'}
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
          {commandText(
            commandState,
            connected,
            simulationRunning,
            sandboxApiAvailable,
            engine,
            activeEngine,
            abidesCapability,
            marketData?.data_source?.provider,
            marketData?.data_source?.source,
          )}
        </span>
      </div>

      <div className="grid gap-3 p-3 xl:grid-cols-[1fr_1fr_1.2fr]">
        <div className="space-y-3 border border-gray-900 bg-black/30 p-3">
          <div className="grid grid-cols-4 gap-2">
            <ToggleButton active={engine === 'sentinel'} onClick={() => setEngine('sentinel')}>
              SENTINEL
            </ToggleButton>
            <ToggleButton
              active={engine === 'abides'}
              disabled={!abidesAvailable}
              onClick={() => setEngine('abides')}
            >
              ABIDES
            </ToggleButton>
            <ToggleButton active={engine === 'groww'} onClick={() => setEngine('groww')}>
              GROWW
            </ToggleButton>
            <ToggleButton active={engine === 'upstox'} onClick={() => setEngine('upstox')}>
              UPSTOX
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
          ) : engine === 'abides' ? (
            <div className="border border-gray-900 bg-black/40 p-2 text-xs text-gray-400">
              <div className="text-[10px] tracking-[0.14em] text-gray-500">CAPABILITY</div>
              <div
                className={`mt-1 ${
                  abidesCapability === 'disabled'
                    ? 'text-[#ff0040]'
                    : abidesCapability === 'available'
                      ? 'text-[#00ff41]'
                      : 'text-[#ffb800]'
                }`}
              >
                {abidesCapabilityText(abidesCapability)}
              </div>
            </div>
          ) : (
            <div className="border border-gray-900 bg-black/40 p-2 text-xs text-gray-400">
              <div className="text-[10px] tracking-[0.14em] text-gray-500">SOURCE</div>
              <div
                className={`mt-1 ${
                  activeLiveStatus === 'connected'
                    ? 'text-[#00ff41]'
                    : activeLiveStatus === 'disconnected'
                      ? 'text-[#ff0040]'
                      : 'text-[#ffb800]'
                }`}
              >
                {activeLiveSource
                  ? `${activeLiveProviderLabel} / ${activeLiveSource.groww_symbol ?? activeLiveSource.instrument_key}`
                  : activeLiveProviderLabel}
              </div>
            </div>
          )}

          {engine === 'groww' ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <TextField label="SYMBOL" value={growwSymbol} onChange={setGrowwSymbol} />
                <label className="block min-w-0">
                  <span className="block truncate text-[10px] tracking-[0.14em] text-gray-500">EXCHANGE</span>
                  <select
                    value={growwExchange}
                    onChange={(event) => setGrowwExchange(event.currentTarget.value)}
                    className="mt-1 h-8 w-full border border-gray-800 bg-black px-2 font-mono text-xs text-gray-100 outline-none focus:border-[#00bfff]"
                  >
                    <option value="NSE">NSE</option>
                    <option value="BSE">BSE</option>
                  </select>
                </label>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="block min-w-0">
                  <span className="block truncate text-[10px] tracking-[0.14em] text-gray-500">SEGMENT</span>
                  <select
                    value={growwSegment}
                    onChange={(event) => setGrowwSegment(event.currentTarget.value)}
                    className="mt-1 h-8 w-full border border-gray-800 bg-black px-2 font-mono text-xs text-gray-100 outline-none focus:border-[#00bfff]"
                  >
                    <option value="CASH">CASH</option>
                    <option value="FNO">FNO</option>
                  </select>
                </label>
                <NumericField
                  label="SPEED"
                  value={speed}
                  min={0.1}
                  max={20}
                  step={0.1}
                  onChange={setSpeed}
                />
              </div>
            </>
          ) : engine === 'upstox' ? (
            <>
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <TextField label="SYMBOL SEARCH" value={upstoxSearchQuery} onChange={setUpstoxSearchQuery} />
                <button
                  type="button"
                  onClick={searchUpstoxInstruments}
                  disabled={commandState === 'loading'}
                  className="mt-4 inline-flex h-8 items-center justify-center border border-[#00bfff] bg-[#00bfff]/10 px-3 text-xs font-bold tracking-[0.12em] text-[#00bfff] disabled:cursor-not-allowed disabled:border-gray-800 disabled:text-gray-600"
                  title="Search Upstox instrument keys"
                >
                  <Search size={13} />
                </button>
              </div>
              {upstoxSearchResults.length > 0 ? (
                <div className="max-h-20 overflow-auto border border-gray-900 bg-black/50 text-[10px]">
                  {upstoxSearchResults.map((result) => (
                    <button
                      key={result.instrument_key}
                      type="button"
                      onClick={() => setUpstoxInstrumentKey(result.instrument_key)}
                      className="grid w-full grid-cols-[0.7fr_1.2fr] gap-2 border-b border-gray-900 px-2 py-1 text-left text-gray-400 hover:bg-[#00bfff]/10 hover:text-gray-100"
                    >
                      <span className="truncate text-[#00bfff]">{result.trading_symbol}</span>
                      <span className="truncate">{result.instrument_key}</span>
                    </button>
                  ))}
                </div>
              ) : null}
              <TextField label="INSTRUMENT KEY" value={upstoxInstrumentKey} onChange={setUpstoxInstrumentKey} />
              <div className="grid grid-cols-2 gap-2">
                <label className="block min-w-0">
                  <span className="block truncate text-[10px] tracking-[0.14em] text-gray-500">UNIT</span>
                  <select
                    value={upstoxUnit}
                    onChange={(event) => setUpstoxUnit(event.currentTarget.value)}
                    className="mt-1 h-8 w-full border border-gray-800 bg-black px-2 font-mono text-xs text-gray-100 outline-none focus:border-[#00bfff]"
                  >
                    <option value="minutes">MINUTES</option>
                    <option value="hours">HOURS</option>
                    <option value="days">DAYS</option>
                    <option value="weeks">WEEKS</option>
                    <option value="months">MONTHS</option>
                  </select>
                </label>
                <NumericField
                  label="SPEED"
                  value={speed}
                  min={0.1}
                  max={20}
                  step={0.1}
                  onChange={setSpeed}
                />
              </div>
            </>
          ) : (
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
          )}
        </div>

        <div className="space-y-3 border border-gray-900 bg-black/30 p-3">
          {engine === 'groww' ? (
            <>
              <TextField label="START TIME" value={growwStartTime} onChange={setGrowwStartTime} />
              <TextField label="END TIME" value={growwEndTime} onChange={setGrowwEndTime} />
              <label className="block">
                <span className="block text-[10px] tracking-[0.14em] text-gray-500">CANDLE INTERVAL</span>
                <select
                  value={growwInterval}
                  onChange={(event) => setGrowwInterval(event.currentTarget.value)}
                  className="mt-1 h-8 w-full border border-gray-800 bg-black px-2 font-mono text-xs text-gray-100 outline-none focus:border-[#00bfff]"
                >
                  <option value="MIN_1">1 MIN</option>
                  <option value="MIN_5">5 MIN</option>
                  <option value="MIN_15">15 MIN</option>
                  <option value="MIN_30">30 MIN</option>
                  <option value="HOUR_1">1 HOUR</option>
                  <option value="DAY_1">1 DAY</option>
                  <option value="WEEK_1">1 WEEK</option>
                </select>
              </label>
            </>
          ) : engine === 'upstox' ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <ToggleButton active={upstoxFeedMode === 'historical'} onClick={() => setUpstoxFeedMode('historical')}>
                  HISTORICAL
                </ToggleButton>
                <ToggleButton active={upstoxFeedMode === 'live'} onClick={() => setUpstoxFeedMode('live')}>
                  LIVE LTP
                </ToggleButton>
              </div>
              {upstoxFeedMode === 'historical' ? (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <TextField label="FROM DATE" value={upstoxFromDate} onChange={setUpstoxFromDate} />
                    <TextField label="TO DATE" value={upstoxToDate} onChange={setUpstoxToDate} />
                  </div>
                  <TextField label="INTERVAL" value={upstoxInterval} onChange={setUpstoxInterval} />
                </>
              ) : (
                <NumericField
                  label="POLL SECONDS"
                  value={upstoxPollInterval}
                  min={1}
                  max={60}
                  onChange={setUpstoxPollInterval}
                />
              )}
              <div className="border border-gray-900 bg-black/40 p-2 text-xs text-gray-400">
                <div className="text-[10px] tracking-[0.14em] text-gray-500">AUTH</div>
                <div className="mt-1 text-[#00bfff]">SERVER TOKEN</div>
              </div>
            </>
          ) : (
            <>
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
            </>
          )}
        </div>

        <div className="border border-gray-900 bg-black/30 p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="text-[10px] tracking-[0.14em] text-gray-500">
              {engine === 'sentinel' ? 'AGENT MIX' : engine === 'abides' ? 'ABIDES AGENTS' : 'DATA SOURCE'}
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
            ) : engine === 'abides' ? (
              <span className="text-[10px] tracking-[0.14em] text-[#00bfff]">{abidesAgentTotal} AGENTS</span>
            ) : (
              <span
                className={`text-[10px] tracking-[0.14em] ${
                  activeLiveStatus === 'connected' ? 'text-[#00ff41]' : activeLiveStatus === 'error' ? 'text-[#ff0040]' : 'text-[#00bfff]'
                }`}
              >
                {activeLiveStatus.toUpperCase()}
              </span>
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
          ) : engine === 'abides' ? (
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
          ) : (
            <div className="grid gap-2 md:grid-cols-3">
              <div className="border border-gray-900 bg-black/40 p-2">
                <div className="text-[10px] tracking-[0.14em] text-gray-500">PROVIDER</div>
                <div className="mt-1 truncate text-xs text-[#00bfff]">{activeLiveProviderLabel}</div>
              </div>
              <div className="border border-gray-900 bg-black/40 p-2">
                <div className="text-[10px] tracking-[0.14em] text-gray-500">
                  {engine === 'upstox' ? 'INSTRUMENT' : 'SYMBOL'}
                </div>
                <div className="mt-1 truncate text-xs text-gray-200">
                  {engine === 'upstox'
                    ? upstoxSource?.instrument_key ?? upstoxInstrumentKey
                    : growwSource?.groww_symbol ?? growwSymbol}
                </div>
              </div>
              <div className="border border-gray-900 bg-black/40 p-2">
                <div className="text-[10px] tracking-[0.14em] text-gray-500">
                  {engine === 'upstox' && upstoxLiveSelected ? 'LTP' : 'BARS'}
                </div>
                <div className="mt-1 truncate text-xs text-gray-200">
                  {engine === 'upstox' && upstoxLiveSelected
                    ? activeLiveSource?.last_price?.toFixed(2) ?? '--'
                    : activeLiveSource?.bars?.toLocaleString() ?? '--'}
                </div>
              </div>
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
              || (engine === 'abides' && !abidesAvailable)
            }
            className="inline-flex items-center gap-2 border border-[#00ff41] bg-[#00ff41]/10 px-3 py-1.5 text-xs font-bold tracking-[0.12em] text-[#00ff41] disabled:cursor-not-allowed disabled:border-gray-800 disabled:text-gray-600"
          >
            <Play size={13} />
            LAUNCH
          </button>
          <button
            type="button"
            onClick={applySpeed}
            disabled={
              commandState === 'loading'
              || !simulationRunning
              || (!sandboxApiAvailable && activeEngine !== 'groww' && activeEngine !== 'upstox')
            }
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
