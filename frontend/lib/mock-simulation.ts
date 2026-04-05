'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  AgentActivity,
  DepthHeatLevel,
  KernelEvent,
  Milestone,
  PriceSpreadPoint,
  SimulationDashboardData,
  TimeSeriesPoint,
  TradeFlowPoint,
} from '@/types/dashboard';
import { useMarketStore } from '@/store/market-store';

const MAX_POINTS = 60;
const MAX_EVENTS = 14;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function timestampLabel(date: Date): string {
  return date.toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' });
}

function nextDepthHeat(midPrice: number, step: number = 0): DepthHeatLevel[] {
  return Array.from({ length: 12 }, (_, idx) => {
    const level = idx + 1;
    const distance = Math.abs(level - 6) + 1;
    const base = 240 / distance;
    // Deterministic noise: calculate based on step and level to avoid hydration mismatches
    const noiseValue = ((step * 17 + level * 23) % 41) - 20.5;
    const noise = noiseValue;
    return {
      level,
      bidDepth: Math.max(20, base + noise + (midPrice % 2) * 6),
      askDepth: Math.max(20, base - noise + ((100 - midPrice) % 2) * 6),
    };
  });
}

function pushPoint<T>(series: T[], point: T): T[] {
  return [...series.slice(-(MAX_POINTS - 1)), point];
}

function nextEvent(step: number, spread: number, imbalance: number): KernelEvent {
  const categories: KernelEvent['type'][] = [
    'Kernel',
    'Order Submission',
    'Order Match',
    'Fill',
    'Cancellation',
    'Latency',
  ];
  const type = categories[Math.floor(Math.random() * categories.length)];
  const severity: KernelEvent['severity'] = spread > 0.12 || Math.abs(imbalance) > 0.4
    ? 'warning'
    : 'info';

  const templates: Record<KernelEvent['type'], string[]> = {
    Kernel: ['Kernel tick committed', 'Synchronized RL step acknowledged'],
    'Order Submission': ['Market maker posted layered quotes', 'Noise agent submitted market order'],
    'Order Match': ['Bid-ask crossed at top level', 'Matching engine resolved queued orders'],
    Fill: ['Passive quote filled by aggressive order', 'Partial fill detected on sell ladder'],
    Cancellation: ['Market maker cancelled stale quote', 'Order timeout triggered cancellation'],
    Latency: ['Injected delayed event reached kernel', 'Latency queue released batched orders'],
  };

  const messageList = templates[type];
  const message = messageList[Math.floor(Math.random() * messageList.length)];

  return {
    id: `ev-${Date.now()}-${step}`,
    time: timestampLabel(new Date()),
    type,
    message,
    severity,
  };
}

function nextAgentActivity(midPrice: number, step: number): AgentActivity {
  const submitted = 850 + step * 3;
  const fills = 590 + step * 2;
  const cancelled = 170 + step;

  const orderStatuses: Array<'Submitted' | 'Filled' | 'Cancelled' | 'Partial Fill'> = [
    'Submitted',
    'Filled',
    'Cancelled',
    'Partial Fill',
  ];

  return {
    marketMakerAction: 'Refreshing two-sided quotes around microprice',
    // Deterministic noise agent action based on step to avoid hydration mismatches
    noiseAgentAction: (step * 7) % 2 === 0
      ? 'Submitting opportunistic BUY market order'
      : 'Submitting opportunistic SELL market order',
    rlAgentStatus: step % 4 === 0 ? 'Policy update pending' : 'Acting with synchronized environment step',
    recentOrders: Array.from({ length: 6 }, (_, idx) => {
      // Deterministic generation based on step and idx
      const pseudoRandom1 = ((step * 13 + idx * 17) % 100) / 100;
      const pseudoRandom2 = ((step * 19 + idx * 23) % 100) / 100;
      const pseudoRandom3 = ((step * 29 + idx * 31) % 100) / 100;
      
      return {
        id: `O-${step}-${idx}`,
        agent: idx % 3 === 0 ? 'RL Agent' : idx % 2 === 0 ? 'Noise Agent' : 'Market Maker',
        side: idx % 2 === 0 ? 'BUY' : 'SELL',
        price: Number((midPrice + (pseudoRandom1 - 0.5) * 0.18).toFixed(3)),
        quantity: Math.floor(30 + pseudoRandom2 * 220),
        status: orderStatuses[Math.floor(pseudoRandom3 * orderStatuses.length)],
      };
    }),
    executionSummary: {
      submitted,
      fills,
      cancelled,
      matchRate: Number(((fills / submitted) * 100).toFixed(1)),
    },
  };
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

export function useSimulationDashboardData(options?: { enabled?: boolean }): SimulationDashboardData {
  const enabled = options?.enabled ?? true;
  const marketData = useMarketStore((s) => s.marketData);
  const connected = useMarketStore((s) => s.connected);

  const seedPrice = marketData?.price ?? 100;

  const [step, setStep] = useState(1);
  const [midPrice, setMidPrice] = useState(seedPrice);
  const [spread, setSpread] = useState(0.08);
  const [inventory, setInventory] = useState(18);
  const [realizedPnl, setRealizedPnl] = useState(1240);
  const [unrealizedPnl, setUnrealizedPnl] = useState(310);
  const [reward, setReward] = useState(42);
  const [imbalance, setImbalance] = useState(0.12);

  const [priceSeries, setPriceSeries] = useState<PriceSpreadPoint[]>([]);
  const [spreadSeries, setSpreadSeries] = useState<TimeSeriesPoint[]>([]);
  const [inventorySeries, setInventorySeries] = useState<TimeSeriesPoint[]>([]);
  const [rewardSeries, setRewardSeries] = useState<TimeSeriesPoint[]>([]);
  const [tradeFlow, setTradeFlow] = useState<TradeFlowPoint[]>([]);
  const [depthHeatmap, setDepthHeatmap] = useState<DepthHeatLevel[]>(nextDepthHeat(seedPrice, 1));
  const [events, setEvents] = useState<KernelEvent[]>([]);
  const [lastUpdateMs, setLastUpdateMs] = useState<number | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    // Delay interval start to allow React hydration to complete (avoids hydration mismatches)
    let intervalId: NodeJS.Timeout | undefined;
    
    const startTimer = setTimeout(() => {
      intervalId = setInterval(() => {
        setStep((prev) => prev + 1);
        setMidPrice((prev) => clamp(prev + (Math.random() - 0.5) * 0.18, 96, 106));
        setSpread((prev) => clamp(prev + (Math.random() - 0.5) * 0.015, 0.03, 0.16));
        setInventory((prev) => clamp(prev + Math.floor((Math.random() - 0.5) * 12), -220, 220));
        setRealizedPnl((prev) => Number((prev + (Math.random() - 0.4) * 12).toFixed(2)));
        setUnrealizedPnl((prev) => Number((prev + (Math.random() - 0.45) * 10).toFixed(2)));
        setReward((prev) => Number((prev + (Math.random() - 0.4) * 2.5).toFixed(3)));
        setImbalance((prev) => clamp(prev + (Math.random() - 0.5) * 0.14, -0.85, 0.85));
      }, 1200);
    }, 100);

    return () => {
      clearTimeout(startTimer);
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const now = timestampLabel(new Date());
    const observedPrice = marketData?.price ?? midPrice;
    const observedSpread = marketData?.spread ?? spread;

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
      value: inventory,
    }));

    setRewardSeries((prev) => pushPoint(prev, {
      time: now,
      value: reward,
    }));

    setTradeFlow((prev) => pushPoint(prev, {
      time: now,
      buyVolume: Math.floor(100 + Math.random() * 260),
      sellVolume: Math.floor(80 + Math.random() * 240),
    }));

    setDepthHeatmap(nextDepthHeat(observedPrice, step));
    setEvents((prev) => [nextEvent(step, observedSpread, imbalance), ...prev].slice(0, MAX_EVENTS));
    setLastUpdateMs(Date.now());
  }, [enabled, step, midPrice, spread, inventory, reward, imbalance, marketData]);

  const agentActivity = useMemo(() => nextAgentActivity(midPrice, step), [midPrice, step]);

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
    prediction: {
      signal: step % 7 === 0 ? 'HOLD' : reward > 0 ? 'BUY' : 'SELL',
      // Keep confidence deterministic on initial render to avoid SSR hydration mismatches.
      confidence: Number((0.55 + Math.min(0.35, (step % 8) * 0.04)).toFixed(3)),
      explanation: 'Mock rule-based signal from momentum, imbalance, and spread penalty.',
    },
    operatingMode: 'SIMULATION',
    liveMarketConnected: false,
    liveMarketSource: 'simulation',
    liveMarketProvider: 'simulation',
    liveMarketFallback: false,
    liveMarketLastUpdateTs: null,
    liveMarketLastUpdateWallTime: null,
    liveMarketStale: false,
    liveMarketLatencyMs: null,
    liveMarketTransport: null,
    liveMarketMessage: null,
    connected,
    dataSource: 'mock',
    loading: false,
    stale: false,
    error: null,
    lastUpdateMs,
  };
}
