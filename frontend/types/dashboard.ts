export interface TradeFlowPoint {
  id: string;
  time: string;
  buyVolume: number;
  sellVolume: number;
}

export interface RecentOrder {
  id: string;
  agent: string;
  side: 'BUY' | 'SELL';
  price: number;
  quantity: number;
  status: 'Submitted' | 'Filled' | 'Cancelled' | 'Partial Fill';
}

export interface ExecutionSummary {
  submitted: number;
  fills: number;
  cancelled: number;
  matchRate: number;
}

export interface AgentActivity {
  recentOrders: RecentOrder[];
  executionSummary: ExecutionSummary;
}

export interface KernelEvent {
  id: string;
  time: string;
  type:
    | 'Kernel'
    | 'Order Submission'
    | 'Order Match'
    | 'Fill'
    | 'Cancellation'
    | 'Latency';
  message: string;
  severity: 'info' | 'warning' | 'critical';
}

export interface SimulationDashboardData {
  tradeFlow: TradeFlowPoint[];
  agentActivity: AgentActivity;
  events: KernelEvent[];
}
