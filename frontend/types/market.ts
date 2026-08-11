// ── SENTINEL Market Types ──────────────────────────────────────────────────

export interface OrderLevel {
  price: number;
  size: number;
}

export interface OrderBook {
  bids: OrderLevel[];
  asks: OrderLevel[];
}

export interface LiquidityPrediction {
  probability?: number;
  stress_score: number;
  health_score: number;
  warning_level: "safe" | "caution" | "warning" | "critical";
  features: Record<string, number>;
  timestamp: number;
  method: "trained_model" | "lobster_nasdaq_model" | "adaptive_stress" | "calibrating";
  market?: string;
  horizon_seconds: number;
}

export interface LargeOrderDetection {
  pattern: "large_level";
  source: "visible_order_book";
  side: "buy" | "sell";
  price?: number;
  estimated_size: number;
  confidence: number;
  depth_share: number;
  size_multiple: number;
}

export interface AgentMetric {
  total_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  halted: boolean;
  agent_type: string;
  position: number;
  num_trades: number;
}

export interface MarketEvent {
  id: string;
  timestamp: number;
  step: number;
  type: "kernel" | "order_submission" | "order_match" | "fill" | "cancellation" | "latency" | string;
  severity: "info" | "warning" | "critical";
  message: string;
  agent_id?: string;
  agent_type?: string;
  order_id?: string;
  trade_id?: string;
  side?: "BUY" | "SELL" | string;
  price?: number;
  quantity?: number;
  status?: "submitted" | "filled" | "cancelled" | "partial" | string;
}

export interface MarketOrderFlow {
  submitted: number;
  fills: number;
  cancelled: number;
  match_rate: number;
  buy_volume: number;
  sell_volume: number;
  submitted_notional?: number;
}

export interface MarketRecentOrder {
  id: string;
  agent_id: string;
  agent_type: string;
  side: "BUY" | "SELL" | string;
  price: number;
  quantity: number;
  status: "submitted" | "filled" | "cancelled" | "partial" | string;
  timestamp: number;
}

export interface MarketScenario {
  name: string;
  label: string;
  description: string;
  phase: string;
  liquidity?: {
    baseline_depth: number;
    depth_depletion: number;
    spread_ratio: number;
    recovery_progress: number;
  };
}

export interface MarketUpdate {
  type: "market_update";
  market?: string;
  venue?: string;
  timestamp: number;
  price: number;
  spread: number;
  depth: number;
  order_book: OrderBook;
  liquidity_prediction: LiquidityPrediction | null;
  large_order_detection: LargeOrderDetection | null;
  agent_metrics: Record<string, AgentMetric>;
  step: number;
  volatility: number;
  session_phase: string;
  activity_multiplier: number;
  scenario: MarketScenario;
  latency_mode: string;
  events?: MarketEvent[];
  order_flow?: MarketOrderFlow;
  recent_orders?: MarketRecentOrder[];
  oracle?: {
    fundamental_value?: number;
    mispricing?: number;
    mispricing_pct?: number;
    observation_noise?: number;
  } | null;
}

export interface Alert {
  id: string;
  message: string;
  level: "caution" | "warning" | "critical";
  timestamp: number;
  dismissed: boolean;
}
