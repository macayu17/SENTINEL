export type ProjectStage = 'Research Prototype' | 'System Integration' | 'Training and Evaluation';

export type MilestoneStatus = 'completed' | 'in-progress' | 'pending';

export interface Milestone {
  phase: string;
  title: string;
  status: MilestoneStatus;
  detail: string;
}

export interface ProjectOverview {
  name: string;
  summary: string;
  currentStage: ProjectStage;
  completed: string[];
  inProgress: string[];
}

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
  marketMakerAction: string;
  noiseAgentAction: string;
  rlAgentStatus: string;
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
  projectOverview: ProjectOverview;
  milestones: Milestone[];
  tradeFlow: TradeFlowPoint[];
  agentActivity: AgentActivity;
  events: KernelEvent[];
}
