'use client';

import { useEffect, useMemo, useState } from 'react';
import { useMarketStore } from '@/store/market-store';
import { useSimulationDashboardData } from '@/lib/mock-simulation';
import {
  DepthHeatLevel,
  KernelEvent,
  Milestone,
  PriceSpreadPoint,
  SimulationDashboardData,
  TimeSeriesPoint,
  TradeFlowPoint,
} from '@/types/dashboard';
import { RecentKernelEvent, RecentOrderUpdate } from '@/types/market';

const MAX_POINTS = 120;
const STALE_AFTER_MS = 6000;

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
    status: 'completed',
    detail: 'Extending behavior diversity with informed and institutional style flow.',
  },
  {
    phase: 'Phase 4',
    title: 'Training, Evaluation, Deployment',
    status: 'completed',
    detail: 'Policy training loops and deployment pathways are under active development.',
  },
];

function pushPoint<T>(series: T[], point: T): T[] {
  return [...series.slice(-(MAX_POINTS - 1)), point];
}

function formatClock(seconds: number): string {
  const hh = Math.floor(seconds / 3600)
    .toString()
    .padStart(2, '0');
  const mm = Math.floor((seconds % 3600) / 60)
    .toString()
    .padStart(2, '0');
  const ss = Math.floor(seconds % 60)
    .toString()
    .padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

function normalizeEvent(event: RecentKernelEvent, idx: number): KernelEvent {
  return {
    id: `evt-${event.ts}-${idx}`,
    time: formatClock(event.ts),
    type: event.type,
    message: event.message,
    severity: event.severity,
  };
}

function mapAgentLabel(agentId: string): 'Market Maker' | 'Noise Agent' | 'RL Agent' {
  const id = agentId.toUpperCase();
  if (id.includes('RL')) return 'RL Agent';
  if (id.includes('NOISE')) return 'Noise Agent';
  return 'Market Maker';
}

function orderStatusCount(orders: RecentOrderUpdate[] | undefined, status: string): number {
  if (!orders) return 0;
  return orders.filter((order) => order.status === status).length;
}

function formatProviderLabel(provider: string): string {
  const normalized = provider.trim().toLowerCase();
  if (normalized === 'nse') return 'nse-style';
  if (normalized === 'broker') return 'broker/exchange live';
  return normalized || 'unknown';
}

export function useDashboardData(): SimulationDashboardData {
  const connected = useMarketStore((s) => s.connected);
  const marketData = useMarketStore((s) => s.marketData);

  const mode = (process.env.NEXT_PUBLIC_DASHBOARD_MODE ?? 'auto').toLowerCase();
  const canUseLive = Boolean(connected && marketData);
  const useMock = mode === 'mock' || (mode === 'auto' && !canUseLive);

  const mock = useSimulationDashboardData({ enabled: useMock });

  const [priceSeries, setPriceSeries] = useState<PriceSpreadPoint[]>([]);
  const [spreadSeries, setSpreadSeries] = useState<TimeSeriesPoint[]>([]);
  const [inventorySeries, setInventorySeries] = useState<TimeSeriesPoint[]>([]);
  const [rewardSeries, setRewardSeries] = useState<TimeSeriesPoint[]>([]);
  const [tradeFlow, setTradeFlow] = useState<TradeFlowPoint[]>([]);
  const [lastUpdateMs, setLastUpdateMs] = useState<number | null>(null);

  useEffect(() => {
    if (!marketData || useMock) {
      return;
    }

    const label = formatClock(marketData.simulation_time ?? marketData.timestamp);
    const midPrice = marketData.mid_price ?? marketData.price;
    const spread = marketData.spread ?? 0;
    const inventory = marketData.inventory ?? 0;
    const reward = marketData.cumulative_reward ?? 0;

    setPriceSeries((prev) =>
      pushPoint(prev, {
        time: label,
        price: Number(midPrice.toFixed(4)),
        spread: Number(spread.toFixed(4)),
      }),
    );

    setSpreadSeries((prev) =>
      pushPoint(prev, {
        time: label,
        value: Number(spread.toFixed(4)),
      }),
    );

    setInventorySeries((prev) =>
      pushPoint(prev, {
        time: label,
        value: inventory,
      }),
    );

    setRewardSeries((prev) =>
      pushPoint(prev, {
        time: label,
        value: Number(reward.toFixed(4)),
      }),
    );

    const trades = marketData.recent_trades ?? [];
    const buyVolume = trades
      .filter((trade) => trade.aggressor_side === 'BUY')
      .reduce((sum, trade) => sum + trade.quantity, 0);
    const sellVolume = trades
      .filter((trade) => trade.aggressor_side === 'SELL')
      .reduce((sum, trade) => sum + trade.quantity, 0);

    setTradeFlow((prev) =>
      pushPoint(prev, {
        time: label,
        buyVolume,
        sellVolume,
      }),
    );

    setLastUpdateMs(Date.now());
  }, [marketData, useMock]);

  const liveData = useMemo<SimulationDashboardData>(() => {
    const levels = marketData?.order_book;
    const bids = levels?.bids ?? [];
    const asks = levels?.asks ?? [];
    const maxLevels = Math.max(12, bids.length, asks.length);
    const heatmap: DepthHeatLevel[] = Array.from({ length: maxLevels }, (_, idx) => ({
      level: idx + 1,
      bidDepth: bids[idx]?.size ?? 0,
      askDepth: asks[idx]?.size ?? 0,
    }));

    const recentOrders = (marketData?.recent_orders ?? []).slice(0, 10).map((order) => ({
      id: order.order_id,
      agent: mapAgentLabel(order.agent_id),
      side: order.side,
      price: order.price,
      quantity: order.quantity,
      status: order.status,
    }));

    const executionSummary = marketData?.execution_summary
      ? {
          submitted: marketData.execution_summary.submitted,
          fills: marketData.execution_summary.fills,
          cancelled: marketData.execution_summary.cancelled,
          matchRate: Number(marketData.execution_summary.match_rate.toFixed(1)),
        }
      : {
          submitted: (marketData?.recent_orders ?? []).length,
          fills: (marketData?.recent_trades ?? []).length,
          cancelled: orderStatusCount(marketData?.recent_orders, 'Cancelled'),
          matchRate: (marketData?.recent_orders?.length ?? 0) > 0
            ? Number((((marketData?.recent_trades?.length ?? 0) / (marketData?.recent_orders?.length ?? 1)) * 100).toFixed(1))
            : 0,
        };

    const stale = !connected || !lastUpdateMs || Date.now() - lastUpdateMs > STALE_AFTER_MS;

    const rlState = marketData?.rl_status?.state ?? 'idle';
    const rlLabel = rlState === 'training'
      ? 'Training'
      : rlState === 'evaluating'
      ? 'Evaluating'
      : 'Idle';

    const agentActions = marketData?.agent_actions ?? {};
    const marketMakerAction =
      Object.entries(agentActions).find(([id]) => id.toUpperCase().startsWith('MM_'))?.[1] ??
      'Awaiting market maker action';
    const noiseAction =
      Object.entries(agentActions).find(([id]) => id.toUpperCase().startsWith('NOISE_'))?.[1] ??
      'Awaiting noise agent action';

    const events = (marketData?.recent_events ?? []).map(normalizeEvent);
    const prediction = marketData?.signal ?? {
      signal: 'HOLD' as const,
      confidence: 0.5,
      explanation: 'Awaiting signal update from backend engine.',
    };
    const rawMode = (marketData?.mode ?? 'SIMULATION').toUpperCase();
    const operatingMode = rawMode === 'LIVE_SHADOW' ? 'LIVE_SHADOW' : 'SIMULATION';
    const liveFeedStatus = marketData?.live_feed;
    const liveMarketProviderRaw = liveFeedStatus?.provider ?? (operatingMode === 'LIVE_SHADOW' ? 'unknown' : 'simulation');
    const liveMarketProvider = formatProviderLabel(liveMarketProviderRaw);
    const liveMarketFallback = Boolean(liveFeedStatus?.fallback_active);
    const liveMarketLastUpdateTs = liveFeedStatus?.last_update_ts ?? null;
    const liveMarketLastUpdateWallTime = liveFeedStatus?.last_update_wall_time ?? null;
    const liveMarketLatencyMs = liveFeedStatus?.latency_ms ?? null;
    const liveMarketStale = Boolean(liveFeedStatus?.stale);
    const liveMarketTransport = liveFeedStatus?.transport ?? null;
    const liveMarketMessage = liveFeedStatus?.message ?? null;
    const liveMarketConnected = operatingMode === 'LIVE_SHADOW'
      ? Boolean(liveFeedStatus?.connected && !liveMarketFallback && liveFeedStatus?.source !== 'mock')
      : false;
    const liveMarketSource = liveFeedStatus?.source ?? (operatingMode === 'LIVE_SHADOW' ? 'mock' : 'simulation');

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
          'Multi-agent realism with institutional and informed behaviors',
          'Training loops and evaluation harness',
          'Production deployment path with monitoring and controls',
        ],
        inProgress: [],
      },
      metrics: {
        midPrice: marketData?.mid_price ?? marketData?.price ?? 0,
        bestBid: marketData?.best_bid ?? 0,
        bestAsk: marketData?.best_ask ?? 0,
        spread: marketData?.spread ?? 0,
        orderBookImbalance: marketData?.order_book_imbalance ?? 0,
        inventory: marketData?.inventory ?? 0,
        realizedPnl: marketData?.realized_pnl ?? 0,
        unrealizedPnl: marketData?.unrealized_pnl ?? 0,
        cumulativeReward: marketData?.cumulative_reward ?? 0,
      },
      priceSeries,
      spreadSeries,
      inventorySeries,
      rewardSeries,
      depthHeatmap: heatmap,
      tradeFlow,
      agentActivity: {
        marketMakerAction,
        noiseAgentAction: noiseAction,
        rlAgentStatus: `${rlLabel}${marketData?.rl_status?.episode ? ` | Episode ${marketData.rl_status.episode}` : ''}`,
        recentOrders,
        executionSummary,
      },
      milestones:
        marketData?.phase_status?.length
          ? marketData.phase_status.map((phase) => ({
              phase: phase.phase,
              title: phase.phase,
              status: phase.status,
              detail: 'Status synced from backend.',
            }))
          : defaultMilestones,
      events,
      prediction: {
        signal: prediction.signal,
        confidence: prediction.confidence,
        explanation: prediction.explanation,
      },
      operatingMode,
      liveMarketConnected,
      liveMarketSource,
      liveMarketProvider,
      liveMarketFallback,
      liveMarketLastUpdateTs,
      liveMarketLastUpdateWallTime,
      liveMarketStale,
      liveMarketLatencyMs,
      liveMarketTransport,
      liveMarketMessage,
      connected,
      dataSource: 'live',
      loading: !marketData,
      stale: stale || liveMarketStale,
      error: connected ? null : 'Disconnected from backend WebSocket stream.',
      lastUpdateMs,
    };
  }, [
    connected,
    lastUpdateMs,
    marketData,
    priceSeries,
    spreadSeries,
    inventorySeries,
    rewardSeries,
    tradeFlow,
  ]);

  if (useMock) {
    return {
      ...mock,
      dataSource: 'mock',
      liveMarketConnected: false,
      liveMarketSource: 'mock',
      liveMarketProvider: 'mock',
      liveMarketFallback: true,
      liveMarketLastUpdateTs: null,
      liveMarketLastUpdateWallTime: null,
      liveMarketStale: false,
      liveMarketLatencyMs: null,
      liveMarketTransport: null,
      liveMarketMessage: null,
      error: connected ? null : mock.error,
    };
  }

  return liveData;
}
