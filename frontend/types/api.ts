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
  latency_mode: LatencyMode;
  speed: number;
  scenario?: string;
  seed?: number;
}

export interface SimulationReportPoint {
  timestamp: number;
  price: number;
  spread: number;
  depth: number;
  imbalance: number;
  signed_volume: number;
  volatility: number;
  scenario_phase?: string | null;
}

export interface SimulationReport {
  status: 'completed';
  generated_at: string;
  run_config: {
    preset: string;
    scenario: string;
    seed: number | null;
    initial_price: number;
    duration_seconds: number;
    elapsed_seconds: number;
    speed: number;
    venue: string;
    agent_count: number;
    latency_mode: string;
    informed_access: boolean;
    steps: number;
  };
  price_path: SimulationReportPoint[];
  order_flow: {
    submitted_orders: number;
    cancel_requests: number;
    accepted_cancels: number;
    terminal_cancels: number;
    summary: {
      submitted: number;
      fills: number;
      cancelled: number;
      match_rate: number;
      buy_volume: number;
      sell_volume: number;
      submitted_notional?: number;
    };
    trades: Array<{
      price: number;
      quantity: number;
      buyer_agent_id: string;
      seller_agent_id: string;
    }>;
  };
  events: Array<Record<string, string | number | boolean | null | undefined>>;
  recent_orders: Array<Record<string, string | number | boolean | null | undefined>>;
  agent_metrics: Record<string, import('./market').AgentMetric & {
    return_pct?: number;
    fees_paid?: number;
  }>;
  warning_timeline: Array<Record<string, string | number | boolean | null | undefined>>;
  validation_metrics: Record<string, number>;
}
