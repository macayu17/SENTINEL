import { getApiBaseUrl } from '@/lib/runtime-config';
import type { OrderBook } from '@/types/market';

export type SimulationMode = 'SANDBOX' | 'LIVE_SHADOW';
export type LatencyMode = 'zero' | 'deterministic' | 'cubic';

export interface SandboxPreset {
  name: string;
  description: string;
  icon: string;
  agents: Record<string, number>;
  oracle: boolean;
  latency: LatencyMode;
}

export interface SandboxScenario {
  name: string;
  label: string;
  description: string;
  seed_depth_multiplier: number;
  liquidity_floor_multiplier: number;
  spread_multiplier: number;
  oracle_sigma_multiplier: number;
  order_ttl_seconds: number;
  volatility_multiplier: number;
  enable_spoofing: boolean;
  institutional_multiplier: number;
}

export interface SandboxCreateRequest {
  preset: string;
  initial_price: number;
  oracle_enabled: boolean;
  oracle_kappa: number;
  oracle_sigma: number;
  latency_mode: LatencyMode;
  speed: number;
  custom_agents?: Record<string, number> | null;
  scenario?: string;
}

export interface AbidesSandboxCreateRequest {
  initial_price: number;
  oracle_enabled: boolean;
  oracle_kappa: number;
  oracle_sigma: number;
  latency_mode: LatencyMode;
  speed: number;
  market_makers: number;
  noise_agents: number;
  informed_agents: number;
}

export interface GrowwReplayRequest {
  groww_symbol: string;
  exchange: string;
  segment: string;
  start_time: string;
  end_time: string;
  candle_interval: string;
  preset?: string;
  custom_agents?: Record<string, number> | null;
  latency_mode?: LatencyMode;
  speed: number;
  scenario?: string;
}

export interface GrowwLiveRequest {
  groww_symbol: string;
  exchange: string;
  segment: string;
  preset?: string;
  custom_agents?: Record<string, number> | null;
  latency_mode?: LatencyMode;
  speed: number;
  poll_interval_seconds: number;
  scenario?: string;
}

export interface UpstoxReplayRequest {
  instrument_key: string;
  unit: string;
  interval: string;
  from_date?: string | null;
  to_date: string;
  preset?: string;
  custom_agents?: Record<string, number> | null;
  latency_mode?: LatencyMode;
  speed: number;
  scenario?: string;
}

export interface UpstoxLiveRequest {
  instrument_key: string;
  preset?: string;
  custom_agents?: Record<string, number> | null;
  latency_mode?: LatencyMode;
  speed: number;
  poll_interval_seconds: number;
  scenario?: string;
}

export interface UpstoxInstrumentResult {
  instrument_key: string;
  trading_symbol: string;
  name: string;
  exchange: string;
  segment: string;
  instrument_type: string;
  isin?: string | null;
  short_name?: string | null;
}

class SentinelAPI {
  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const url = `${getApiBaseUrl()}${path}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json() as { detail?: string; error?: string };
        detail = payload.detail ?? payload.error ?? detail;
      } catch {
        // keep status text fallback
      }
      throw new Error(`API error: ${detail}`);
    }
    return response.json();
  }

  async health() {
    return this.request<{
      status: string;
      simulation_active: boolean;
      connected_clients: number;
      mode: SimulationMode;
    }>('/api/health');
  }

  async startSimulation() {
    return this.request<{ status: string; agents: number; initial_price: number }>('/api/simulation/start', { method: 'POST' });
  }

  async stopSimulation() {
    return this.request<{ status: string }>('/api/simulation/stop', { method: 'POST' });
  }

  async setSimulationMode(mode: 'SANDBOX') {
    return this.request<{ status: string; mode: string }>('/api/simulation/mode', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    });
  }

  async getSandboxPresets() {
    return this.request<Record<string, SandboxPreset>>('/api/sandbox/presets');
  }

  async getSandboxCapabilities() {
    return this.request<{ abides: boolean }>('/api/sandbox/capabilities');
  }

  async getSandboxScenarios() {
    return this.request<{ scenarios: SandboxScenario[] }>('/api/sandbox/scenarios');
  }

  async createSandbox(config: SandboxCreateRequest) {
    return this.request<{
      status: string;
      preset: string;
      agents: number;
      oracle_enabled: boolean;
      speed: number;
      scenario: string;
    }>('/api/sandbox/create', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async createAbidesSandbox(config: AbidesSandboxCreateRequest) {
    return this.request<{
      status: string;
      engine: 'ABIDES';
      oracle_enabled: boolean;
      oracle_auto_enabled: boolean;
      speed: number;
      agents: number;
    }>('/api/sandbox/abides/create', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async fetchGrowwHistorical(config: GrowwReplayRequest) {
    return this.request<{
      provider: 'groww';
      source: 'historical';
      status: string;
      mode: SimulationMode;
      groww_symbol: string;
      name: string;
      currency: string;
      last_close: number;
      bars: number;
      price_preview: number[];
    }>('/api/live-shadow/groww/fetch', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async startGrowwReplay(config: GrowwReplayRequest) {
    return this.request<{
      status: string;
      mode: 'LIVE_SHADOW';
      provider: 'groww';
      source: 'historical_replay';
      groww_symbol: string;
      initial_price: number;
      bars: number;
      replay_steps: number;
      realized_vol: number;
      agents: number;
      speed: number;
      scenario?: string;
    }>('/api/live-shadow/groww/replay', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async fetchGrowwQuote(config: Pick<GrowwLiveRequest, 'groww_symbol' | 'exchange' | 'segment'>) {
    return this.request<{
      provider: 'groww';
      source: 'live_depth';
      status: string;
      mode: 'LIVE_SHADOW';
      groww_symbol: string;
      exchange: string;
      segment: string;
      last_price: number;
      ltq?: number | null;
      volume?: number | null;
      previous_close?: number | null;
      depth_source?: string | null;
      order_book?: OrderBook | null;
    }>('/api/live-shadow/groww/quote', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async startGrowwLive(config: GrowwLiveRequest) {
    return this.request<{
      status: string;
      mode: 'LIVE_SHADOW';
      provider: 'groww';
      source: 'live_depth';
      groww_symbol: string;
      initial_price: number;
      last_price: number;
      depth_source: string;
      poll_interval_seconds: number;
      agents: number;
      speed: number;
      scenario?: string;
    }>('/api/live-shadow/groww/live', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async fetchUpstoxHistorical(config: UpstoxReplayRequest) {
    return this.request<{
      provider: 'upstox';
      source: 'historical';
      status: string;
      mode: SimulationMode;
      instrument_key: string;
      name: string;
      currency: string;
      last_close: number;
      bars: number;
      price_preview: number[];
    }>('/api/live-shadow/upstox/fetch', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async searchUpstoxInstruments(config: {
    query: string;
    exchanges?: string;
    segments?: string;
    page_number?: number;
    records?: number;
  }) {
    const params = new URLSearchParams({
      query: config.query,
      exchanges: config.exchanges ?? 'NSE',
      segments: config.segments ?? 'EQ',
      page_number: String(config.page_number ?? 1),
      records: String(config.records ?? 10),
    });
    return this.request<{
      provider: 'upstox';
      source: 'instrument_search';
      status: string;
      query: string;
      results: UpstoxInstrumentResult[];
    }>(`/api/live-shadow/upstox/instruments?${params.toString()}`);
  }

  async fetchUpstoxLtp(config: { instrument_key: string }) {
    return this.request<{
      provider: 'upstox';
      source: 'live_ltp';
      status: string;
      mode: 'LIVE_SHADOW';
      instrument_key: string;
      last_price: number;
      ltq?: number | null;
      volume?: number | null;
      previous_close?: number | null;
    }>('/api/live-shadow/upstox/ltp', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async startUpstoxLive(config: UpstoxLiveRequest) {
    return this.request<{
      status: string;
      mode: 'LIVE_SHADOW';
      provider: 'upstox';
      source: 'live_depth';
      instrument_key: string;
      initial_price: number;
      last_price: number;
      depth_source: string;
      poll_interval_seconds: number;
      agents: number;
      speed: number;
      scenario?: string;
    }>('/api/live-shadow/upstox/live', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async startUpstoxReplay(config: UpstoxReplayRequest) {
    return this.request<{
      status: string;
      mode: 'LIVE_SHADOW';
      provider: 'upstox';
      source: 'historical_replay';
      instrument_key: string;
      initial_price: number;
      bars: number;
      replay_steps: number;
      realized_vol: number;
      agents: number;
      speed: number;
      scenario?: string;
    }>('/api/live-shadow/upstox/replay', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async setSandboxSpeed(speed: number) {
    return this.request<{ speed: number } | { error: string }>('/api/sandbox/speed', {
      method: 'PUT',
      body: JSON.stringify({ speed }),
    });
  }

  async setAbidesSpeed(speed: number) {
    return this.request<{ speed: number } | { error: string }>('/api/sandbox/abides/speed', {
      method: 'PUT',
      body: JSON.stringify({ speed }),
    });
  }

  async getLiquidityPrediction() {
    return this.request('/api/prediction/liquidity');
  }

  async getLargeOrderDetection() {
    return this.request('/api/prediction/large-order');
  }

  async getAgentMetrics() {
    return this.request('/api/agents/metrics');
  }

  async getMarketSnapshot() {
    return this.request('/api/market/snapshot');
  }

  async exportSimulation() {
    return this.request<Record<string, unknown>>('/api/simulation/export');
  }
}

export const api = new SentinelAPI();
