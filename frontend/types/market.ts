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
  realized_pnl?: number;
  unrealized_pnl?: number;
  return_pct?: number;
  sharpe_ratio: number;
  agent_type: string;
  position: number;
  num_trades: number;
}

export interface RecentOrderUpdate {
  ts: number;
  order_id: string;
  agent_id: string;
  side: 'BUY' | 'SELL';
  order_type: 'LIMIT' | 'MARKET';
  price: number;
  quantity: number;
  status: 'Submitted' | 'Cancelled' | 'Filled' | 'Partial Fill';
}

export interface RecentTradeUpdate {
  ts: number;
  trade_id: string;
  price: number;
  quantity: number;
  buyer_agent_id: string;
  seller_agent_id: string;
  aggressor_side: 'BUY' | 'SELL';
}

export interface RecentKernelEvent {
  ts: number;
  type:
    | 'Kernel'
    | 'Order Submission'
    | 'Order Match'
    | 'Fill'
    | 'Cancellation'
    | 'Latency';
  severity: 'info' | 'warning' | 'critical';
  message: string;
  metadata?: Record<string, unknown>;
}

export interface ExecutionSummaryUpdate {
  submitted: number;
  fills: number;
  cancelled: number;
  match_rate: number;
}

export interface RlStatus {
  state: 'training' | 'idle' | 'evaluating';
  episode?: number;
  training_step?: number;
}

export interface SignalOutput {
  signal: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  explanation: string;
  components?: Record<string, number>;
}

export interface LiveFeedStatus {
  connected: boolean;
  source: 'binance' | 'mock' | 'simulation' | string;
  provider?: 'binance' | 'nse' | 'broker' | 'mock' | 'simulation' | string;
  fallback_active?: boolean;
  last_update_ts?: number | null;
  last_update_wall_time?: number | null;
  stale?: boolean;
  latency_ms?: number | null;
  transport?: 'stream' | 'poll' | 'fallback' | 'synthetic' | 'skeleton' | string;
  message?: string;
}

export interface MarketUpdate {
  type: "market_update";
  data_contract_version?: string;
  timestamp: number;
  price: number;
  mid_price?: number;
  best_bid?: number | null;
  best_ask?: number | null;
  spread: number;
  depth: number;
  order_book_imbalance?: number;
  order_book: OrderBook;
  liquidity_prediction: LiquidityPrediction;
  large_order_detection: LargeOrderDetection | null;
  agent_metrics: Record<string, AgentMetric>;
  inventory?: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  cumulative_reward?: number;
  recent_orders?: RecentOrderUpdate[];
  recent_trades?: RecentTradeUpdate[];
  recent_events?: RecentKernelEvent[];
  agent_actions?: Record<string, string>;
  execution_summary?: ExecutionSummaryUpdate;
  rl_status?: RlStatus;
  phase_status?: Array<{ phase: string; status: 'completed' | 'in-progress' | 'pending' }>;
  simulation_time?: number;
  time_to_close?: number;
  step: number;
  volatility: number;
  signal?: SignalOutput;
  live_feed?: LiveFeedStatus;
  mode: "SIMULATION" | "LIVE_SHADOW" | "SANDBOX";
}

export interface Alert {
  id: string;
  message: string;
  level: "caution" | "warning" | "critical";
  timestamp: number;
  dismissed: boolean;
}
