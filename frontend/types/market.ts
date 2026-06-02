// ── SENTINEL Market Types ──────────────────────────────────────────────────

export type SimulationMode = 'SANDBOX' | 'LIVE_SHADOW';

export interface OrderLevel {
  price: number;
  size: number;
}

export interface OrderBook {
  bids: OrderLevel[];
  asks: OrderLevel[];
}

export interface LiquidityPrediction {
  probability: number;
  health_score: number;
  warning_level: "safe" | "caution" | "warning" | "critical";
  features: Record<string, number>;
  timestamp: number;
}

export interface LargeOrderDetection {
  pattern: "iceberg" | "twap";
  side: "buy" | "sell";
  estimated_size: number;
  confidence: number;
  completion_pct?: number;
  executed_so_far?: number;
  avg_interval?: number;
  avg_order_size?: number;
  detected_orders?: number;
  impact?: {
    expected_impact_pct: number;
    expected_impact_dollars: number;
    size_vs_depth_ratio: number;
    market_conditions: string;
  };
}

export interface AgentMetric {
  total_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  sharpe_ratio: number;
  agent_type: string;
  position: number;
  num_trades: number;
}

export interface MarketDataSource {
  provider: string;
  source: string;
  status: "connected" | "loading" | "error" | "disconnected" | string;
  groww_symbol?: string;
  instrument_key?: string;
  exchange?: string;
  segment?: string;
  candle_interval?: string;
  scenario?: string;
  unit?: string;
  interval?: string;
  bars?: number;
  replay_steps?: number;
  period_start?: string;
  period_end?: string;
  last_price?: number;
  ltq?: number | null;
  volume?: number | null;
  previous_close?: number | null;
  timestamp?: string | null;
  total_buy_quantity?: number | null;
  total_sell_quantity?: number | null;
  depth_source?: string | null;
  depth_note?: string | null;
  order_book_source?: string | null;
  order_book_history?: string | null;
  depth_model?: Record<string, number | string | boolean | null> | null;
  order_book?: OrderBook | null;
  poll_interval_seconds?: number;
  last_update_step?: number;
  error?: string;
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

export interface MarketUpdate {
  type: "market_update" | "abides_update";
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
  mode: SimulationMode;
  engine?: "ABIDES";
  data_source?: MarketDataSource | null;
  events?: MarketEvent[];
  order_flow?: MarketOrderFlow;
  recent_orders?: MarketRecentOrder[];
  oracle?: {
    fundamental_value?: number;
    observed_value?: number;
    mispricing?: number;
    relative_mispricing?: number;
  } | null;
}

export interface Alert {
  id: string;
  message: string;
  level: "caution" | "warning" | "critical";
  timestamp: number;
  dismissed: boolean;
}
