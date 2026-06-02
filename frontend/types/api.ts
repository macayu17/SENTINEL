import type { OrderBook } from '@/types/market';

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

export interface GrowwQuoteResponse {
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
}
