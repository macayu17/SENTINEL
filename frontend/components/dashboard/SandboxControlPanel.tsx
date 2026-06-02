'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Download, Play, Search, SlidersHorizontal, Square } from 'lucide-react';
import {
  api,
  type LatencyMode,
  type SandboxPreset,
  type SandboxScenario,
  type UpstoxInstrumentResult,
} from '@/lib/api-client';
import { useMarketStore } from '@/store/market-store';

type SandboxEngine = 'sentinel' | 'abides' | 'groww' | 'upstox';
type GrowwFeedMode = 'historical' | 'live';
type UpstoxFeedMode = 'historical' | 'live';
type CommandState = 'idle' | 'loading' | 'success' | 'error';
type AbidesCapability = 'available' | 'disabled' | 'unverified';
type LiveShadowProvider = 'groww' | 'upstox';

const FIELD_BASE_CLASS =
  'mt-1 h-10 min-h-10 w-full border border-gray-800 bg-black px-2 font-mono text-xs text-gray-100 outline-none transition-colors focus:border-[#00bfff] disabled:cursor-not-allowed disabled:text-gray-600';
const TEXT_FIELD_CLASS = `${FIELD_BASE_CLASS} cursor-text`;
const NUMERIC_FIELD_CLASS = TEXT_FIELD_CLASS;
const SELECT_FIELD_CLASS = `${FIELD_BASE_CLASS} cursor-pointer appearance-auto pr-8 [color-scheme:dark]`;
const DATE_FIELD_CLASS = `${FIELD_BASE_CLASS} cursor-pointer [color-scheme:dark]`;

const AGENT_ORDER = [
  'MarketMaker',
  'HFT',
  'Institutional',
  'Retail',
  'Informed',
  'Noise',
  'LiquidityTrader',
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
      LiquidityTrader: 1,
      Momentum: 2,
      MeanReversion: 2,
      Spoofing: 0,
      Sentiment: 5,
    },
    oracle: false,
    latency: 'deterministic',
  },
};

const FALLBACK_SCENARIOS: SandboxScenario[] = [
  {
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
  },
  {
    name: 'market_open',
    label: 'Market Open',
    description: 'Wider opening spread and faster quote churn.',
    seed_depth_multiplier: 1.35,
    liquidity_floor_multiplier: 1.25,
    spread_multiplier: 2.5,
    oracle_sigma_multiplier: 1,
    order_ttl_seconds: 8,
    volatility_multiplier: 1.4,
    enable_spoofing: false,
    institutional_multiplier: 1,
  },
  {
    name: 'liquidity_shock',
    label: 'Liquidity Shock',
    description: 'Thin-book warning stress run.',
    seed_depth_multiplier: 0.28,
    liquidity_floor_multiplier: 0.35,
    spread_multiplier: 4,
    oracle_sigma_multiplier: 1,
    order_ttl_seconds: 5,
    volatility_multiplier: 2.2,
    enable_spoofing: false,
    institutional_multiplier: 1,
  },
  {
    name: 'institutional_execution',
    label: 'Institutional Execution',
    description: 'Elevated parent-order flow.',
    seed_depth_multiplier: 1.15,
    liquidity_floor_multiplier: 1,
    spread_multiplier: 1.25,
    oracle_sigma_multiplier: 1,
    order_ttl_seconds: 20,
    volatility_multiplier: 1.2,
    enable_spoofing: false,
    institutional_multiplier: 2,
  },
  {
    name: 'volatility_spike',
    label: 'Volatility Spike',
    description: 'High-volatility quoting stress.',
    seed_depth_multiplier: 0.75,
    liquidity_floor_multiplier: 0.8,
    spread_multiplier: 3,
    oracle_sigma_multiplier: 2.5,
    order_ttl_seconds: 7,
    volatility_multiplier: 2.8,
    enable_spoofing: false,
    institutional_multiplier: 1,
  },
  {
    name: 'spoofing_stress',
    label: 'Spoofing Stress',
    description: 'Adversarial spoofing detector run.',
    seed_depth_multiplier: 0.9,
    liquidity_floor_multiplier: 0.8,
    spread_multiplier: 1.75,
    oracle_sigma_multiplier: 1,
    order_ttl_seconds: 6,
    volatility_multiplier: 1.5,
    enable_spoofing: true,
    institutional_multiplier: 1,
  },
  {
    name: 'close_auction',
    label: 'Close / Auction',
    description: 'Closing-style liquidity concentration.',
    seed_depth_multiplier: 1.8,
    liquidity_floor_multiplier: 1.6,
    spread_multiplier: 1.6,
    oracle_sigma_multiplier: 1,
    order_ttl_seconds: 12,
    volatility_multiplier: 1,
    enable_spoofing: false,
    institutional_multiplier: 1.4,
  },
];

const DEFAULT_AGENT_COUNTS = FALLBACK_PRESETS.balanced.agents;
const DEFAULT_GROWW_REPLAY = {
  groww_symbol: 'RELIANCE',
  exchange: 'NSE',
  segment: 'CASH',
  start_time: '2025-09-24T09:15',
  end_time: '2025-09-24T15:30',
  candle_interval: 'MIN_30',
};
const DEFAULT_UPSTOX_REPLAY = {
  instrument_key: 'NSE_EQ|INE002A01018',
  unit: 'minutes',
  interval: '30',
  from_date: '2025-01-01',
  to_date: '2025-01-01',
};

function findBestUpstoxMatch(
  results: UpstoxInstrumentResult[],
  query: string,
): UpstoxInstrumentResult | null {
  const normalized = query.trim().toUpperCase();
  if (!normalized) return null;
  return results.find((result) => result.trading_symbol.toUpperCase() === normalized)
    ?? results.find((result) => result.instrument_key.toUpperCase() === normalized)
    ?? null;
}

function toFiniteNumber(value: number, fallback: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function toGrowwApiTime(value: string): string {
  const normalized = value.trim().replace('T', ' ');
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(normalized)) {
    return `${normalized}:00`;
  }
  return normalized;
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
  if (state === 'loading') return 'COMMAND PENDING';
  if (state === 'error') return 'COMMAND REJECTED';
  if (engine === 'abides' && abidesCapability !== 'disabled' && !sandboxApiAvailable) return 'ABIDES PROBE';

  if (liveDataProvider === 'groww' && running) {
    return liveDataSource === 'live_depth' ? 'GROWW LIVE RUNNING' : 'GROWW REPLAY RUNNING';
  }
  if (liveDataProvider === 'upstox' && running) {
    return liveDataSource === 'live_depth' || liveDataSource === 'live_ltp'
      ? 'UPSTOX LIVE RUNNING'
      : 'UPSTOX REPLAY RUNNING';
  }

  if (activeEngine === 'groww' && running) return 'GROWW REPLAY RUNNING';
  if (activeEngine === 'upstox' && running) return 'UPSTOX REPLAY RUNNING';
  if (engine === 'groww') return connected ? 'GROWW READY' : 'BACKEND OFFLINE';
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

function isLiveShadowProvider(provider?: string | null): provider is LiveShadowProvider {
  return provider === 'groww' || provider === 'upstox';
}

function isLiveProviderSource(source?: string | null): boolean {
  return source === 'live_depth' || source === 'live_ltp';
}

function liveProviderLabel(
  provider: LiveShadowProvider,
  source: { source?: string | null } | null,
  fallbackMode: GrowwFeedMode | UpstoxFeedMode,
): string {
  const live = source?.source ? isLiveProviderSource(source.source) : fallbackMode === 'live';
  if (provider === 'upstox') {
    return live ? 'UPSTOX LIVE DEPTH' : 'UPSTOX HISTORICAL';
  }
  return live ? 'GROWW LIVE DEPTH' : 'GROWW HISTORICAL';
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
        className={NUMERIC_FIELD_CLASS}
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
        className={TEXT_FIELD_CLASS}
      />
    </label>
  );
}

function DateField({
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
        type="date"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={DATE_FIELD_CLASS}
      />
    </label>
  );
}

function DateTimeField({
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
        type="datetime-local"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={DATE_FIELD_CLASS}
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  children,
  onChange,
}: {
  label: string;
  value: string;
  children: ReactNode;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block min-w-0">
      <span className="block truncate text-[10px] tracking-[0.14em] text-gray-500">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={SELECT_FIELD_CLASS}
      >
        {children}
      </select>
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
  const [scenarios, setScenarios] = useState<SandboxScenario[]>(FALLBACK_SCENARIOS);
  const [scenario, setScenario] = useState('normal');
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
  const [growwFeedMode, setGrowwFeedMode] = useState<GrowwFeedMode>('historical');
  const [growwPollInterval, setGrowwPollInterval] = useState(5);
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
  const selectedScenario = scenarios.find((item) => item.name === scenario) ?? FALLBACK_SCENARIOS[0];
  const abidesAvailable = abidesCapability !== 'disabled';
  const selectedAgentCounts = customAgentsEnabled ? agentCounts : selectedPreset.agents;
  const totalAgents = useMemo(
    () => Object.values(selectedAgentCounts).reduce((sum, count) => sum + Math.max(0, count), 0),
    [selectedAgentCounts],
  );
  const abidesAgentTotal = marketMakers + noiseAgents + informedAgents;
  const liveDataSource = marketData?.data_source ?? null;
  const liveDataProvider = isLiveShadowProvider(liveDataSource?.provider) ? liveDataSource.provider : null;
  const growwSource = liveDataProvider === 'groww' ? liveDataSource : null;
  const upstoxSource = liveDataProvider === 'upstox' ? liveDataSource : null;
  const growwStatus = growwSource?.status ?? (engine === 'groww' && !connected ? 'disconnected' : 'idle');
  const upstoxStatus = upstoxSource?.status ?? (engine === 'upstox' && !connected ? 'disconnected' : 'idle');
  const activeLiveProvider = liveDataProvider ?? (isLiveShadowProvider(activeEngine) ? activeEngine : null);
  const selectedLiveProvider = isLiveShadowProvider(engine) ? engine : null;
  const displayLiveProvider = simulationRunning && activeLiveProvider ? activeLiveProvider : selectedLiveProvider;
  const displayLiveSource = displayLiveProvider === 'upstox'
    ? upstoxSource
    : displayLiveProvider === 'groww'
      ? growwSource
      : null;
  const displayLiveStatus = displayLiveProvider === 'upstox'
    ? upstoxStatus
    : displayLiveProvider === 'groww'
      ? growwStatus
      : 'idle';
  const displayLiveProviderLabel = displayLiveProvider === 'upstox'
    ? liveProviderLabel('upstox', displayLiveSource, upstoxFeedMode)
    : displayLiveProvider === 'groww'
      ? liveProviderLabel('groww', displayLiveSource, growwFeedMode)
      : 'LIVE SHADOW';
  const displayLiveIsLive = displayLiveSource?.source
    ? isLiveProviderSource(displayLiveSource.source)
    : displayLiveProvider === 'upstox'
      ? upstoxFeedMode === 'live'
      : displayLiveProvider === 'groww'
        ? growwFeedMode === 'live'
        : false;

  useEffect(() => {
    let cancelled = false;

    const loadSandboxMetadata = async () => {
      const [presetsResult, capabilitiesResult, scenariosResult] = await Promise.allSettled([
        api.getSandboxPresets(),
        api.getSandboxCapabilities(),
        api.getSandboxScenarios(),
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

      if (scenariosResult.status === 'fulfilled') {
        setScenarios(scenariosResult.value.scenarios);
        if (!scenariosResult.value.scenarios.some((item) => item.name === scenario)) {
          setScenario('normal');
        }
      } else {
        setScenarios(FALLBACK_SCENARIOS);
      }

      setCommandState('idle');
      if (
        presetsResult.status === 'fulfilled'
        && capabilitiesResult.status === 'fulfilled'
        && scenariosResult.status === 'fulfilled'
      ) {
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
  }, [preset, scenario]);

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
      const bestMatch = findBestUpstoxMatch(response.results, upstoxSearchQuery);
      if (bestMatch) {
        setUpstoxInstrumentKey(bestMatch.instrument_key);
      }
      setCommandState('success');
      setCommandMessage(
        bestMatch
          ? `Upstox search / selected ${bestMatch.trading_symbol}.`
          : `Upstox search / ${response.results.length} matches.`,
      );
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
        if (growwFeedMode === 'live') {
          const response = await api.startGrowwLive({
            groww_symbol: growwSymbol.trim(),
            exchange: growwExchange.trim().toUpperCase(),
            segment: growwSegment.trim().toUpperCase(),
            preset,
            custom_agents: customAgentsEnabled ? selectedAgentCounts : null,
            latency_mode: latencyMode,
            speed: safeSpeed,
            poll_interval_seconds: toFiniteNumber(growwPollInterval, 5, 1, 60),
            scenario,
          });
          resetSimulationData();
          setActiveEngine('groww');
          setSimulationMode('LIVE_SHADOW');
          setSimulationRunning(true);
          setCommandState('success');
          setCommandMessage(
            `Groww live depth / ${response.groww_symbol} / ${selectedScenario.label} / ${response.last_price.toFixed(2)} / ${response.poll_interval_seconds}s`,
          );
          return;
        }

        const response = await api.startGrowwReplay({
          groww_symbol: growwSymbol.trim(),
          exchange: growwExchange.trim().toUpperCase(),
          segment: growwSegment.trim().toUpperCase(),
          start_time: toGrowwApiTime(growwStartTime),
          end_time: toGrowwApiTime(growwEndTime),
          candle_interval: growwInterval.trim().toUpperCase(),
          preset,
          custom_agents: customAgentsEnabled ? selectedAgentCounts : null,
          latency_mode: latencyMode,
          speed: safeSpeed,
          scenario,
        });
        resetSimulationData();
        setActiveEngine('groww');
        setSimulationMode('LIVE_SHADOW');
        setSimulationRunning(true);
        setCommandState('success');
        setCommandMessage(
          `Groww historical replay / ${response.groww_symbol} / ${selectedScenario.label} / ${response.bars} bars / ${response.speed}x`,
        );
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
            scenario,
          });
          resetSimulationData();
          setActiveEngine('upstox');
          setSimulationMode('LIVE_SHADOW');
          setSimulationRunning(true);
          setCommandState('success');
          setCommandMessage(
            `Upstox live depth / ${response.instrument_key} / ${selectedScenario.label} / ${response.last_price.toFixed(2)} / ${response.poll_interval_seconds}s`,
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
          scenario,
        });
        resetSimulationData();
        setActiveEngine('upstox');
        setSimulationMode('LIVE_SHADOW');
        setSimulationRunning(true);
        setCommandState('success');
        setCommandMessage(
          `Upstox historical replay / ${response.instrument_key} / ${selectedScenario.label} / ${response.bars} bars / ${response.speed}x`,
        );
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
          scenario,
        });
        setCommandMessage(
          `${response.preset.toUpperCase()} online / ${response.agents} agents / ${response.scenario} / speed ${response.speed}x`,
        );
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

  const exportRun = async () => {
    setCommandState('loading');
    setCommandMessage('Exporting run snapshot...');

    try {
      const snapshot = await api.exportSimulation();
      const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      anchor.href = url;
      anchor.download = `sentinel-run-${timestamp}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);

      setCommandState('success');
      setCommandMessage('Run snapshot exported.');
    } catch (error) {
      setCommandState('error');
      setCommandMessage(error instanceof Error ? error.message : 'Export failed.');
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
                className={SELECT_FIELD_CLASS}
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
                  displayLiveStatus === 'connected'
                    ? 'text-[#00ff41]'
                    : displayLiveStatus === 'disconnected'
                      ? 'text-[#ff0040]'
                      : 'text-[#ffb800]'
                }`}
              >
                {displayLiveSource
                  ? `${displayLiveProviderLabel} / ${displayLiveSource.groww_symbol ?? displayLiveSource.instrument_key}`
                  : displayLiveProviderLabel}
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
                    className={SELECT_FIELD_CLASS}
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
                    className={SELECT_FIELD_CLASS}
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
                <SelectField
                  label="MATCHES"
                  value={
                    upstoxSearchResults.some((result) => result.instrument_key === upstoxInstrumentKey)
                      ? upstoxInstrumentKey
                      : ''
                  }
                  onChange={setUpstoxInstrumentKey}
                >
                  <option value="" disabled>
                    SELECT INSTRUMENT
                  </option>
                  {upstoxSearchResults.map((result) => (
                    <option key={result.instrument_key} value={result.instrument_key}>
                      {result.trading_symbol} / {result.instrument_key}
                    </option>
                  ))}
                </SelectField>
              ) : null}
              <TextField label="INSTRUMENT KEY" value={upstoxInstrumentKey} onChange={setUpstoxInstrumentKey} />
              <div className="grid grid-cols-2 gap-2">
                <label className="block min-w-0">
                  <span className="block truncate text-[10px] tracking-[0.14em] text-gray-500">UNIT</span>
                  <select
                    value={upstoxUnit}
                    onChange={(event) => setUpstoxUnit(event.currentTarget.value)}
                    className={SELECT_FIELD_CLASS}
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

          {engine !== 'abides' ? (
            <SelectField label="SCENARIO" value={scenario} onChange={setScenario}>
              {scenarios.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.label} / {item.name}
                </option>
              ))}
            </SelectField>
          ) : null}
        </div>

        <div className="space-y-3 border border-gray-900 bg-black/30 p-3">
          {engine === 'groww' ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <ToggleButton active={growwFeedMode === 'historical'} onClick={() => setGrowwFeedMode('historical')}>
                  HISTORICAL
                </ToggleButton>
                <ToggleButton active={growwFeedMode === 'live'} onClick={() => setGrowwFeedMode('live')}>
                  LIVE DEPTH
                </ToggleButton>
              </div>
              {growwFeedMode === 'historical' ? (
                <>
                  <DateTimeField label="START TIME" value={growwStartTime} onChange={setGrowwStartTime} />
                  <DateTimeField label="END TIME" value={growwEndTime} onChange={setGrowwEndTime} />
                  <label className="block">
                    <span className="block text-[10px] tracking-[0.14em] text-gray-500">CANDLE INTERVAL</span>
                    <select
                      value={growwInterval}
                      onChange={(event) => setGrowwInterval(event.currentTarget.value)}
                      className={SELECT_FIELD_CLASS}
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
              ) : (
                <>
                  <NumericField
                    label="POLL SECONDS"
                    value={growwPollInterval}
                    min={1}
                    max={60}
                    onChange={setGrowwPollInterval}
                  />
                  <div className="border border-gray-900 bg-black/40 p-2 text-xs text-gray-400">
                    <div className="text-[10px] tracking-[0.14em] text-gray-500">DEPTH</div>
                    <div className="mt-1 text-[#00bfff]">QUOTE / MODELED FALLBACK</div>
                  </div>
                </>
              )}
            </>
          ) : engine === 'upstox' ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <ToggleButton active={upstoxFeedMode === 'historical'} onClick={() => setUpstoxFeedMode('historical')}>
                  HISTORICAL
                </ToggleButton>
                <ToggleButton active={upstoxFeedMode === 'live'} onClick={() => setUpstoxFeedMode('live')}>
                  LIVE DEPTH
                </ToggleButton>
              </div>
              {upstoxFeedMode === 'historical' ? (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <DateField label="FROM DATE" value={upstoxFromDate} onChange={setUpstoxFromDate} />
                    <DateField label="TO DATE" value={upstoxToDate} onChange={setUpstoxToDate} />
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
                  className={SELECT_FIELD_CLASS}
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
                  displayLiveStatus === 'connected' ? 'text-[#00ff41]' : displayLiveStatus === 'error' ? 'text-[#ff0040]' : 'text-[#00bfff]'
                }`}
              >
                {displayLiveStatus.toUpperCase()}
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
            <div className="grid gap-2 md:grid-cols-4">
              <div className="border border-gray-900 bg-black/40 p-2">
                <div className="text-[10px] tracking-[0.14em] text-gray-500">PROVIDER</div>
                <div className="mt-1 truncate text-xs text-[#00bfff]">{displayLiveProviderLabel}</div>
              </div>
              <div className="border border-gray-900 bg-black/40 p-2">
                <div className="text-[10px] tracking-[0.14em] text-gray-500">
                  {displayLiveProvider === 'upstox' ? 'INSTRUMENT' : 'SYMBOL'}
                </div>
                <div className="mt-1 truncate text-xs text-gray-200">
                  {displayLiveProvider === 'upstox'
                    ? displayLiveSource?.instrument_key ?? upstoxInstrumentKey
                    : displayLiveSource?.groww_symbol ?? growwSymbol}
                </div>
              </div>
              <div className="border border-gray-900 bg-black/40 p-2">
                <div className="text-[10px] tracking-[0.14em] text-gray-500">
                  {displayLiveIsLive ? 'LTP' : 'BARS'}
                </div>
                <div className="mt-1 truncate text-xs text-gray-200">
                  {displayLiveIsLive
                    ? displayLiveSource?.last_price?.toFixed(2) ?? '--'
                    : displayLiveSource?.bars?.toLocaleString() ?? '--'}
                </div>
              </div>
              <div className="border border-gray-900 bg-black/40 p-2">
                <div className="text-[10px] tracking-[0.14em] text-gray-500">DEPTH</div>
                <div className="mt-1 truncate text-xs text-gray-200">
                  {displayLiveSource?.depth_source === 'provider_live'
                    ? 'LIVE BOOK'
                    : displayLiveSource?.depth_source === 'modeled_from_ohlcv'
                      ? 'MODELED OHLCV'
                      : displayLiveSource?.depth_source === 'modeled_live_fallback'
                        ? 'MODELED LIVE'
                        : displayLiveSource?.depth_source
                          ? 'MODELED FALLBACK'
                          : '--'}
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
            onClick={exportRun}
            disabled={commandState === 'loading' || !simulationRunning || activeEngine === 'abides'}
            className="inline-flex items-center gap-2 border border-[#ffb800] bg-[#ffb800]/10 px-3 py-1.5 text-xs font-bold tracking-[0.12em] text-[#ffb800] disabled:cursor-not-allowed disabled:border-gray-800 disabled:text-gray-600"
          >
            <Download size={13} />
            EXPORT
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
