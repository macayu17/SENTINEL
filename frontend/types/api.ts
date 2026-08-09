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
  oracle_kappa?: number;
  oracle_sigma?: number;
  latency_mode: LatencyMode;
  speed: number;
  custom_agents?: Record<string, number> | null;
  scenario?: string;
  seed?: number;
}
