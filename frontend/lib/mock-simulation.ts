'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  AgentActivity,
  DepthHeatLevel,
  KernelEvent,
  Milestone,
  PriceSpreadPoint,
  RecentOrder,
  SimulationDashboardData,
  TimeSeriesPoint,
  TradeFlowPoint,
} from '@/types/dashboard';
import {
  MarketEvent,
  MarketOrderFlow,
  MarketRecentOrder,
  MarketUpdate,
  OrderBook,
} from '@/types/market';
import { useMarketStore } from '@/store/market-store';

const MAX_POINTS = 60;
const MAX_EVENTS = 14;

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

  if (timestamp > 1_000_000_000) {
    return timestampLabel(new Date(timestamp * 1000));
  }

  return `T+${timestamp.toFixed(2)}`;
}

function nextDepthHeat(midPrice: number): DepthHeatLevel[] {
  return Array.from({ length: 12 }, (_, idx) => ({
    level: idx + 1,
    bidDepth: Math.max(0, Math.round(midPrice ? 120 / (idx + 1) : 0)),
    askDepth: Math.max(0, Math.round(midPrice ? 120 / (idx + 1) : 0)),
  }));
}

function pushPoint<T>(series: T[], point: T): T[] {
  return [...series.slice(-(MAX_POINTS - 1)), point];
}

function buildDepthHeatmap(orderBook: OrderBook | undefined, fallbackPrice: number): DepthHeatLevel[] {
  const bids = orderBook?.bids ?? [];
  const asks = orderBook?.asks ?? [];
  if (!bids.length && !asks.length) {
    return nextDepthHeat(fallbackPrice);
  }

  return Array.from({ length: 12 }, (_, idx) => ({
    level: idx + 1,
    bidDepth: bids[idx]?.size ?? 0,
    askDepth: asks[idx]?.size ?? 0,
  }));
}

function computeOrderBookImbalance(orderBook: OrderBook | undefined): number {
  const bidDepth = (orderBook?.bids ?? []).reduce((sum, level) => sum + level.size, 0);
  const askDepth = (orderBook?.asks ?? []).reduce((sum, level) => sum + level.size, 0);
  return (bidDepth - askDepth) / Math.max(1, bidDepth + askDepth);
}

function mapBackendEventType(type: string): KernelEvent['type'] {
  if (type === 'order_submission') return 'Order Submission';
  if (type === 'order_match') return 'Order Match';
  if (type === 'fill') return 'Fill';
  if (type === 'cancellation') return 'Cancellation';
  if (type === 'latency') return 'Latency';
  return 'Kernel';
}

function mapBackendEvents(backendEvents: MarketEvent[] | undefined): KernelEvent[] {
  return (backendEvents ?? []).slice(0, MAX_EVENTS).map((event) => ({
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

function mapBackendRecentOrders(backendOrders: MarketRecentOrder[]): RecentOrder[] {
  return backendOrders.slice(0, 8).map((order) => ({
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
  const metrics = Object.values(marketData.agent_metrics ?? {});
  const marketMakerCount = metrics.filter((metric) => /market/i.test(metric.agent_type)).length;
  const noiseCount = metrics.filter((metric) => /noise/i.test(metric.agent_type)).length;
  const rlCount = metrics.filter((metric) => /rl|policy/i.test(metric.agent_type)).length;

  return {
    marketMakerAction: marketMakerCount > 0
      ? `Tracking ${marketMakerCount} market-maker agents against the live book.`
      : 'No active market-maker agent trace in the latest packet.',
    noiseAgentAction: flow
      ? `Recent aggressor flow B ${flow.buy_volume} / S ${flow.sell_volume} across ${noiseCount} noise agents.`
      : 'Awaiting order-flow counters from the exchange loop.',
    rlAgentStatus: rlCount > 0
      ? `Policy agent active across ${rlCount} trace streams.`
      : 'No active RL policy agent in this run.',
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
  if (!orderFlow) {
    return previous;
  }

  return pushPoint(previous, {
    id: `tf-${step}-${orderFlow.submitted}-${orderFlow.fills}`,
    time,
    buyVolume: orderFlow.buy_volume,
    sellVolume: orderFlow.sell_volume,
  });
}

const defaultMilestones: Milestone[] = [
  {
    phase: 'Phase 1',
    title: 'Simulator and LOB',
    status: 'completed',
    detail: 'Event-driven kernel, matching logic, and microstructure metrics are operational.',
  },
  {
    phase: 'Phase 2',
    title: 'RL Environment',
    status: 'completed',
    detail: 'Gymnasium-style environment with synchronized RL stepping is integrated.',
  },
  {
    phase: 'Phase 3',
    title: 'Multi-Agent Realism',
    status: 'in-progress',
    detail: 'Extending behavior diversity with informed and institutional style flow.',
  },
  {
    phase: 'Phase 4',
    title: 'Training, Evaluation, Deployment',
    status: 'in-progress',
    detail: 'Policy training loops and deployment pathways are under active development.',
  },
];

export function useSimulationDashboardData(): SimulationDashboardData {
  const marketData = useMarketStore((s) => s.marketData);
  const connected = useMarketStore((s) => s.connected);
  const simulationRunning = useMarketStore((s) => s.simulationRunning);
  const feedActive = connected && simulationRunning;

  const seedPrice = marketData?.price ?? 100;

  const [midPrice, setMidPrice] = useState(seedPrice);
  const [spread, setSpread] = useState(0);
  const [inventory, setInventory] = useState(0);
  const [realizedPnl, setRealizedPnl] = useState(0);
  const [unrealizedPnl, setUnrealizedPnl] = useState(0);
  const [reward, setReward] = useState(0);
  const [imbalance, setImbalance] = useState(0);

  const [priceSeries, setPriceSeries] = useState<PriceSpreadPoint[]>([]);
  const [spreadSeries, setSpreadSeries] = useState<TimeSeriesPoint[]>([]);
  const [inventorySeries, setInventorySeries] = useState<TimeSeriesPoint[]>([]);
  const [rewardSeries, setRewardSeries] = useState<TimeSeriesPoint[]>([]);
  const [tradeFlow, setTradeFlow] = useState<TradeFlowPoint[]>([]);
  const [depthHeatmap, setDepthHeatmap] = useState<DepthHeatLevel[]>(nextDepthHeat(seedPrice));
  const [events, setEvents] = useState<KernelEvent[]>([]);

  useEffect(() => {
    if (!feedActive || !marketData) {
      return;
    }

    const now = timestampLabel(new Date());
    const observedPrice = marketData.price;
    const observedSpread = marketData.spread;
    const agentMetrics = Object.values(marketData.agent_metrics ?? {});
    const aggregateInventory = agentMetrics.reduce((sum, metric) => sum + metric.position, 0);
    const aggregateRealized = agentMetrics.reduce((sum, metric) => sum + metric.realized_pnl, 0);
    const aggregateUnrealized = agentMetrics.reduce((sum, metric) => sum + metric.unrealized_pnl, 0);
    const aggregateReward = Number(((aggregateRealized + aggregateUnrealized) / 1000).toFixed(3));

    setMidPrice(observedPrice);
    setSpread(observedSpread);
    setInventory(aggregateInventory);
    setRealizedPnl(Number(aggregateRealized.toFixed(2)));
    setUnrealizedPnl(Number(aggregateUnrealized.toFixed(2)));
    setReward(aggregateReward);
    setImbalance(Number(computeOrderBookImbalance(marketData.order_book).toFixed(3)));

    setPriceSeries((prev) => pushPoint(prev, {
      time: now,
      price: Number(observedPrice.toFixed(3)),
      spread: Number(observedSpread.toFixed(4)),
    }));

    setSpreadSeries((prev) => pushPoint(prev, {
      time: now,
      value: Number(observedSpread.toFixed(4)),
    }));

    setInventorySeries((prev) => pushPoint(prev, {
      time: now,
      value: aggregateInventory,
    }));

    setRewardSeries((prev) => pushPoint(prev, {
      time: now,
      value: aggregateReward,
    }));

    setTradeFlow((prev) => mergeBackendTradeFlow(prev, marketData.order_flow, marketData.step, now));

    setDepthHeatmap(buildDepthHeatmap(marketData.order_book, observedPrice));
    setEvents(mapBackendEvents(marketData.events));
  }, [feedActive, marketData]);

  useEffect(() => {
    if (feedActive) {
      return;
    }

    setMidPrice(seedPrice);
    setSpread(0);
    setInventory(0);
    setRealizedPnl(0);
    setUnrealizedPnl(0);
    setReward(0);
    setImbalance(0);
    setPriceSeries([]);
    setSpreadSeries([]);
    setInventorySeries([]);
    setRewardSeries([]);
    setTradeFlow([]);
    setEvents([]);
    setDepthHeatmap(nextDepthHeat(seedPrice));
  }, [feedActive, seedPrice]);

  const agentActivity = useMemo(() => {
    if (feedActive && marketData) {
      return buildBackendAgentActivity(marketData);
    }

    const statusMessage = !connected
      ? 'Backend offline. Awaiting websocket reconnect.'
      : 'Simulation paused. No policy steps are being issued.';

    return {
      marketMakerAction: !connected
        ? 'Quote engine standing by for live market feed'
        : 'Quote engine idle while simulation is stopped',
      noiseAgentAction: !connected
        ? 'Order flow generator paused with no backend session'
        : 'Noise flow idle until simulation resumes',
      rlAgentStatus: statusMessage,
      recentOrders: [],
      executionSummary: {
        submitted: 0,
        fills: 0,
        cancelled: 0,
        matchRate: 0,
      },
    };
  }, [connected, feedActive, marketData]);

  const bestBid = Number((midPrice - spread / 2).toFixed(3));
  const bestAsk = Number((midPrice + spread / 2).toFixed(3));

  return {
    projectOverview: {
      name: 'SENTINEL',
      summary:
        'A market microstructure intelligence platform for early warning signals, policy training, and resilient execution research.',
      currentStage: 'System Integration',
      completed: [
        'Limit order book and matching kernel',
        'Market maker and noise agent simulation',
        'Event-driven simulator with delayed events',
        'Gymnasium-style RL environment with synchronized stepping',
        'Core market microstructure metrics and test simulations',
      ],
      inProgress: [
        'Multi-agent realism with institutional and informed behaviors',
        'Training loops and evaluation harness',
        'Production deployment path with monitoring and controls',
      ],
    },
    metrics: {
      midPrice: Number(midPrice.toFixed(3)),
      bestBid,
      bestAsk,
      spread: Number(spread.toFixed(4)),
      orderBookImbalance: Number(imbalance.toFixed(3)),
      inventory,
      realizedPnl,
      unrealizedPnl,
      cumulativeReward: reward,
    },
    priceSeries,
    spreadSeries,
    inventorySeries,
    rewardSeries,
    depthHeatmap,
    tradeFlow,
    agentActivity,
    milestones: defaultMilestones,
    events,
    connected,
  };
}
