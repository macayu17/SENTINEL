'use client';

import { useEffect, useMemo, useState } from 'react';
import type {
  AgentActivity,
  KernelEvent,
  RecentOrder,
  SimulationDashboardData,
  TradeFlowPoint,
} from '@/types/dashboard';
import type {
  MarketEvent,
  MarketOrderFlow,
  MarketRecentOrder,
  MarketUpdate,
} from '@/types/market';
import { useMarketStore } from '@/store/market-store';

const MAX_POINTS = 60;
const MAX_EVENTS = 14;

const DEFAULT_PROJECT_OVERVIEW = {
  name: 'Sentinel',
  summary: 'Market microstructure simulation and liquidity-risk research.',
  currentStage: 'System Integration' as const,
  completed: ['Event-driven simulator', 'Order-book metrics'],
  inProgress: ['Scenario realism', 'Liquidity shock evaluation'],
};

const DEFAULT_MILESTONES = [
  {
    phase: 'Phase 1',
    title: 'Simulator and LOB',
    status: 'completed' as const,
    detail: 'Event-driven kernel, matching logic, and microstructure metrics are operational.',
  },
  {
    phase: 'Phase 2',
    title: 'Market Realism',
    status: 'in-progress' as const,
    detail: 'Scenario drivers and liquidity diagnostics are under active development.',
  },
];

function timestampLabel(date: Date): string {
  return date.toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour12: false,
    minute: '2-digit',
    second: '2-digit',
  });
}

function simulationTimeLabel(timestamp: number | undefined): string {
  if (typeof timestamp !== 'number' || !Number.isFinite(timestamp)) {
    return timestampLabel(new Date());
  }
  return timestamp > 1_000_000_000
    ? timestampLabel(new Date(timestamp * 1000))
    : `T+${timestamp.toFixed(2)}`;
}

function pushPoint<T>(series: T[], point: T): T[] {
  return [...series.slice(-(MAX_POINTS - 1)), point];
}

function mapBackendEventType(type: string): KernelEvent['type'] {
  if (type === 'order_submission') return 'Order Submission';
  if (type === 'order_match') return 'Order Match';
  if (type === 'fill') return 'Fill';
  if (type === 'cancellation') return 'Cancellation';
  if (type === 'latency') return 'Latency';
  return 'Kernel';
}

function mapBackendEvents(events: MarketEvent[] | undefined): KernelEvent[] {
  return (events ?? []).slice(0, MAX_EVENTS).map((event) => ({
    id: event.id,
    time: simulationTimeLabel(event.timestamp),
    type: mapBackendEventType(event.type),
    message: event.message,
    severity: event.severity,
  }));
}

function mapBackendOrderStatus(status: string): RecentOrder['status'] {
  if (status === 'filled') return 'Filled';
  if (status === 'cancelled') return 'Cancelled';
  if (status === 'partial') return 'Partial Fill';
  return 'Submitted';
}

function mapBackendRecentOrders(orders: MarketRecentOrder[]): RecentOrder[] {
  return orders.slice(0, 8).map((order) => ({
    id: order.id,
    agent: order.agent_type ? `${order.agent_type} ${order.agent_id}` : order.agent_id,
    side: order.side === 'SELL' ? 'SELL' : 'BUY',
    price: Number(order.price.toFixed(3)),
    quantity: order.quantity,
    status: mapBackendOrderStatus(order.status),
  }));
}

function buildBackendAgentActivity(marketData: MarketUpdate): AgentActivity {
  const flow = marketData.order_flow;
  return {
    marketMakerAction: 'Quote engine active in the simulator.',
    noiseAgentAction: flow
      ? `Aggressor flow B ${flow.buy_volume} / S ${flow.sell_volume}.`
      : 'Awaiting order-flow counters from the simulator.',
    rlAgentStatus: 'No policy agent attached to this SIM run.',
    recentOrders: mapBackendRecentOrders(marketData.recent_orders ?? []),
    executionSummary: {
      submitted: flow?.submitted ?? 0,
      fills: flow?.fills ?? 0,
      cancelled: flow?.cancelled ?? 0,
      matchRate: Number((flow?.match_rate ?? 0).toFixed(1)),
    },
  };
}

function mergeBackendTradeFlow(
  previous: TradeFlowPoint[],
  orderFlow: MarketOrderFlow | undefined,
  step: number,
  time: string,
): TradeFlowPoint[] {
  if (!orderFlow) return previous;
  return pushPoint(previous, {
    id: `tf-${step}-${orderFlow.submitted}-${orderFlow.fills}`,
    time,
    buyVolume: orderFlow.buy_volume,
    sellVolume: orderFlow.sell_volume,
  });
}

export function useSimulationDashboardData(): SimulationDashboardData {
  const marketData = useMarketStore((state) => state.marketData);
  const connected = useMarketStore((state) => state.connected);
  const simulationRunning = useMarketStore((state) => state.simulationRunning);
  const feedActive = connected && simulationRunning;
  const [tradeFlow, setTradeFlow] = useState<TradeFlowPoint[]>([]);
  const [events, setEvents] = useState<KernelEvent[]>([]);

  useEffect(() => {
    if (!feedActive || !marketData) return;
    const now = timestampLabel(new Date());
    setTradeFlow((previous) => mergeBackendTradeFlow(
      previous,
      marketData.order_flow,
      marketData.step,
      now,
    ));
    setEvents(mapBackendEvents(marketData.events));
  }, [feedActive, marketData]);

  useEffect(() => {
    if (feedActive) return;
    setTradeFlow([]);
    setEvents([]);
  }, [feedActive]);

  const agentActivity = useMemo<AgentActivity>(() => {
    if (feedActive && marketData) return buildBackendAgentActivity(marketData);

    return {
      marketMakerAction: 'Quote engine idle while simulation is stopped.',
      noiseAgentAction: 'Order flow idle until simulation resumes.',
      rlAgentStatus: 'No policy agent attached to this SIM run.',
      recentOrders: [],
      executionSummary: { submitted: 0, fills: 0, cancelled: 0, matchRate: 0 },
    };
  }, [feedActive, marketData]);

  return {
    projectOverview: DEFAULT_PROJECT_OVERVIEW,
    milestones: DEFAULT_MILESTONES,
    tradeFlow,
    agentActivity,
    events,
  };
}
