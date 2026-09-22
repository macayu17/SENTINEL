'use client';

import Link from 'next/link';
import DepthInspector from '@/components/dashboard/DepthInspector';
import { memo, useEffect, useMemo, useState } from 'react';
import type {
  AgentActivity,
  KernelEvent,
  RecentOrder,
  TradeFlowPoint,
} from '@/types/dashboard';
import AlertBanner from '@/components/AlertBanner';
import PriceChart from '@/components/PriceChart';
import LiquidityGauge from '@/components/LiquidityGauge';
import LargeOrderDetector from '@/components/LargeOrderDetector';
import AgentMetricsPanel from '@/components/AgentMetricsPanel';
import ThemeToggle from '@/components/ThemeToggle';
import InfoTip from '@/components/InfoTip';
import RippleField from '@/components/RippleField';
import WorkspaceDock from '@/components/WorkspaceDock';
import SandboxControlPanel from '@/components/dashboard/SandboxControlPanel';
import { useMarketWebSocket } from '@/lib/websocket';
import { useSimulationDashboardData } from '@/lib/dashboard-data';
import { api } from '@/lib/api-client';
import { useMarketStore } from '@/store/market-store';
import type { MarketUpdate } from '@/types/market';

type MetricTone = 'positive' | 'negative' | 'warning' | 'accent' | 'neutral';

interface DashboardMetricCell {
  label: string;
  value: string;
  tone: MetricTone;
}

function finiteNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function formatClock(value: number): string {
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = Math.floor(value % 60);
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds
    .toString()
    .padStart(2, '0')}`;
}

function formatISTWallClock(date: Date): string {
  return date.toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function eventClass(severity: KernelEvent['severity']): string {
  if (severity === 'critical') return 'before:bg-[#ff0040]';
  if (severity === 'warning') return 'before:bg-[#ffb800]';
  return 'before:bg-[#00bfff]';
}

function feedStateLabel(connected: boolean, simulationRunning: boolean, activeLabel: string): string {
  if (!connected) return 'BACKEND OFFLINE';
  if (!simulationRunning) return 'SIM PAUSED';
  return activeLabel;
}

function sourceBadgeLabel(connected: boolean): string {
  if (!connected) return 'SOURCE: DISCONNECTED';
  return 'SIM: NASDAQ';
}

function formatCurrency(value: number, digits = 2, symbol = '$'): string {
  if (!Number.isFinite(value)) {
    return `${symbol}--`;
  }
  return `${symbol}${value.toFixed(digits)}`;
}

function buildFooterFeedLabel(
  marketData: MarketUpdate | null,
  simulationRunning: boolean,
): string {
  if (!simulationRunning) {
    return 'SIM IDLE';
  }

  if (!marketData) {
    return 'SIM RUNNING | FEED SYNCING';
  }

  return [
    formatCurrency(marketData.price),
    `SPR ${finiteNumber(marketData.spread).toFixed(4)}`,
    `DEPTH ${finiteNumber(marketData.depth).toLocaleString()}`,
    `SIM VOL ${finiteNumber(marketData.volatility).toFixed(4)}`,
  ].join(' | ');
}

function orderSideClass(side: RecentOrder['side']): string {
  return side === 'BUY' ? 'text-[#00ff41]' : 'text-[#ff0040]';
}

function orderStatusClass(status: RecentOrder['status']): string {
  if (status === 'Filled') return 'text-[#00ff41]';
  if (status === 'Cancelled') return 'text-[#ff0040]';
  if (status === 'Partial Fill') return 'text-[#ffb800]';
  return 'text-[#00bfff]';
}

const TerminalEventPanel = memo(function TerminalEventPanel({
  events,
  connected,
  simulationRunning,
}: {
  events: KernelEvent[];
  connected: boolean;
  simulationRunning: boolean;
}) {
  const statusLabel = feedStateLabel(connected, simulationRunning, 'LIVE FEED');
  const emptyLabel = !connected ? 'BACKEND OFFLINE' : 'EVENT STREAM IDLE';
  const importantEvents = events.filter((event) => event.severity !== 'info' || event.type === 'Fill');

  return (
    <div className="terminal-panel h-full">
      <div className="panel-header">
        <span className="panel-tag">KERNEL EVENT TAPE</span>
        <span className="text-[10px] tracking-[0.16em] text-gray-500">{statusLabel}</span>
      </div>

      <div className="max-h-[340px] overflow-auto px-1">
        {importantEvents.length === 0 ? (
          <div className="border border-dashed border-gray-800 px-3 py-6 text-center text-xs tracking-[0.14em] text-gray-600">
            {emptyLabel}
          </div>
        ) : (
          importantEvents.map((event) => (
            <div key={event.id} className="border-b border-gray-800/70 py-3 pl-3">
              <div className="flex items-center justify-between gap-3 text-[10px] tracking-[0.14em]">
                <span className={`relative pl-3 text-gray-500 before:absolute before:left-0 before:top-1/2 before:size-1.5 before:-translate-y-1/2 before:rounded-full ${eventClass(event.severity)}`}>{event.type.toUpperCase()}</span>
                <span className="text-gray-600">{event.time}</span>
              </div>
              <div className="mt-1 text-xs text-gray-200">{event.message}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
});

const TerminalTradeFlowPanel = memo(function TerminalTradeFlowPanel({
  data,
  connected,
  simulationRunning,
}: {
  data: TradeFlowPoint[];
  connected: boolean;
  simulationRunning: boolean;
}) {
  const rows = useMemo(() => data.slice(-8).reverse(), [data]);
  const peakVolume = useMemo(
    () => Math.max(1, ...rows.flatMap((row) => [row.buyVolume, row.sellVolume])),
    [rows],
  );
  const statusLabel = feedStateLabel(connected, simulationRunning, 'BUY VS SELL');
  const emptyLabel = !connected ? 'BACKEND OFFLINE' : 'FLOW BUFFER IDLE';

  return (
    <div className="terminal-panel h-full">
      <div className="panel-header">
        <span className="panel-tag">FLOW LADDER</span>
        <span className="text-[10px] tracking-[0.16em] text-gray-500">{statusLabel}</span>
      </div>

      <div className="space-y-2 p-3">
        {rows.length === 0 ? (
          <div className="border border-dashed border-gray-800 px-3 py-6 text-center text-xs tracking-[0.14em] text-gray-600">
            {emptyLabel}
          </div>
        ) : (
          rows.map((row) => (
            <div key={row.id} className="space-y-1 border border-gray-900 bg-black/30 p-2">
              <div className="flex items-center justify-between text-[10px] tracking-[0.14em] text-gray-500">
                <span>{row.time}</span>
                <span>
                  B {row.buyVolume} / S {row.sellVolume}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="h-2 bg-gray-950">
                  <div
                    className="h-full bg-[#00ff41]"
                    style={{ width: `${(row.buyVolume / peakVolume) * 100}%` }}
                  />
                </div>
                <div className="h-2 bg-gray-950">
                  <div
                    className="ml-auto h-full bg-[#ff0040]"
                    style={{ width: `${(row.sellVolume / peakVolume) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
});

const TerminalActivityPanel = memo(function TerminalActivityPanel({
  activity,
  connected,
  simulationRunning,
}: {
  activity: AgentActivity;
  connected: boolean;
  simulationRunning: boolean;
}) {
  const statusLabel = feedStateLabel(connected, simulationRunning, 'AGENT TRACE');

  return (
    <div className="terminal-panel h-full">
      <div className="panel-header">
        <span className="panel-tag">EXECUTION MONITOR</span>
        <span className="text-[10px] tracking-[0.16em] text-gray-500">{statusLabel}</span>
      </div>

      <div className="grid gap-3 p-3 xl:grid-cols-[0.95fr_1.1fr]">
        <div>
          <div className="grid grid-cols-2 gap-2">
            <div className="border border-gray-900 bg-black/30 p-3">
              <div className="text-[10px] tracking-[0.16em] text-gray-500">SUBMITTED</div>
              <div className="mt-1 text-lg font-bold text-[#00bfff]">
                {activity.executionSummary.submitted}
              </div>
            </div>
            <div className="border border-gray-900 bg-black/30 p-3">
              <div className="text-[10px] tracking-[0.16em] text-gray-500">MATCH RATE</div>
              <div className="mt-1 text-lg font-bold text-[#00ff41]">
                {activity.executionSummary.matchRate}%
              </div>
            </div>
            <div className="border border-gray-900 bg-black/30 p-3">
              <div className="text-[10px] tracking-[0.16em] text-gray-500">FILLS</div>
              <div className="mt-1 text-lg font-bold text-[#00ff41]">
                {activity.executionSummary.fills}
              </div>
            </div>
            <div className="border border-gray-900 bg-black/30 p-3">
              <div className="text-[10px] tracking-[0.16em] text-gray-500">CANCELS</div>
              <div className="mt-1 text-lg font-bold text-[#ffb800]">
                {activity.executionSummary.cancelled}
              </div>
            </div>
          </div>
        </div>

        <div className="execution-orders border border-gray-900 bg-black/30">
          <div className="grid grid-cols-12 gap-2 border-b border-gray-900 px-3 py-2 text-[10px] tracking-[0.14em] text-gray-500">
            <div className="col-span-2">ID</div>
            <div className="col-span-3">AGENT</div>
            <div className="col-span-1 text-center">SD</div>
            <div className="col-span-2 text-right">PX</div>
            <div className="col-span-2 text-right">QTY</div>
            <div className="col-span-2 text-right">STATUS</div>
          </div>
          <div className="max-h-[260px] overflow-auto">
            {activity.recentOrders.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs tracking-[0.14em] text-gray-600">
                {!connected ? 'BACKEND OFFLINE' : 'NO ACTIVE AGENT TRACE'}
              </div>
            ) : (
              activity.recentOrders.map((order, index) => (
                <div
                  key={`${order.id}-${order.status}-${index}`}
                  className="grid grid-cols-12 gap-2 border-b border-gray-950 px-3 py-2 text-xs text-gray-300"
                >
                  <div className="col-span-2 text-gray-500">{order.id}</div>
                  <div className="col-span-3 truncate">{order.agent}</div>
                  <div className={`col-span-1 text-center ${orderSideClass(order.side)}`}>
                    {order.side === 'BUY' ? 'B' : 'S'}
                  </div>
                  <div className="col-span-2 text-right">{formatCurrency(order.price, 3)}</div>
                  <div className="col-span-2 text-right">{order.quantity}</div>
                  <div className={`col-span-2 text-right ${orderStatusClass(order.status)}`}>
                    {order.status.toUpperCase()}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
});

function TerminalClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return <span>{now ? formatISTWallClock(now) : '--:--:--'}</span>;
}

export default function DashboardPage() {
  const { connect } = useMarketWebSocket();

  const dashboard = useSimulationDashboardData();
  const marketData = useMarketStore((state) => state.marketData);
  const connected = useMarketStore((state) => state.connected);
  const simulationRunning = useMarketStore((state) => state.simulationRunning);
  const resetSimulationData = useMarketStore((state) => state.resetSimulationData);
  const setSimulationRunning = useMarketStore((state) => state.setSimulationRunning);

  useEffect(() => {
    let cancelled = false;

    const syncHealth = async () => {
      try {
        const health = await api.health();
        if (cancelled) {
          return;
        }
        setSimulationRunning(health.simulation_active);
        if (!health.simulation_active) {
          resetSimulationData();
        }
      } catch {
        // Ignore health sync failures and let websocket state drive the shell.
      }
    };

    void syncHealth();

    return () => {
      cancelled = true;
    };
  }, [resetSimulationData, setSimulationRunning]);

  const focusMarket = () => document.getElementById('market')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const causalCells = useMemo<DashboardMetricCell[]>(() => {
    const flow = marketData?.order_flow;
    const flowDelta = (flow?.buy_volume ?? 0) - (flow?.sell_volume ?? 0);
    const basisBps = finiteNumber(marketData?.oracle?.mispricing_pct) * 100;
    const hasOracle = typeof marketData?.oracle?.fundamental_value === 'number';
    const cells: DashboardMetricCell[] = [
      {
        label: 'REGIME',
        value: marketData?.scenario?.label?.toUpperCase() ?? 'AWAITING RUN',
        tone: 'warning',
      },
      { label: 'SESSION', value: marketData?.session_phase ?? '--', tone: 'neutral' },
      {
        label: 'ACTIVITY',
        value: `${finiteNumber(marketData?.activity_multiplier, 1).toFixed(2)}x`,
        tone: 'accent',
      },
      { label: 'LATENCY', value: marketData?.latency_mode ?? '--', tone: 'accent' },
      {
        label: 'AGGRESSOR FLOW',
        value: `${flowDelta >= 0 ? '+' : ''}${flowDelta.toLocaleString()}`,
        tone: flowDelta > 0 ? 'positive' : flowDelta < 0 ? 'negative' : 'neutral',
      },
    ];
    if (hasOracle) {
      cells.splice(4, 0,
        {
          label: 'LATENT VALUE',
          value: formatCurrency(finiteNumber(marketData?.oracle?.fundamental_value), 4),
          tone: 'accent',
        },
        {
          label: 'REFERENCE GAP',
          value: `${basisBps >= 0 ? '+' : ''}${basisBps.toFixed(1)} BPS`,
          tone: Math.abs(basisBps) >= 10 ? 'warning' : 'positive',
        },
      );
    }
    return cells;
  }, [marketData]);
  const footerFeedLabel = useMemo(
    () => buildFooterFeedLabel(marketData, simulationRunning),
    [marketData, simulationRunning],
  );

  return <div className="research-shell dashboard-shell">
    <header className="site-nav"><Link href="/" className="brand"><i className="brand-mark" aria-hidden="true" />sentinel</Link><span className="nav-source">{sourceBadgeLabel(connected)}</span><nav aria-label="Primary navigation"><Link href="/docs">Documentation</Link></nav><ThemeToggle /></header>
    <main id="workspace">
      <div className="workspace-heading"><RippleField className="workspace-ripple" /><div className="workspace-heading-copy"><div className="eyebrow">Workspace / {marketData?.scenario?.label ?? 'new experiment'}</div><h1>The market, under observation.</h1><p>{marketData ? `${Object.keys(marketData.agent_metrics).length} agents · ${marketData.venue ?? marketData.market} simulation` : 'Configure an experiment to observe the market.'}</p></div><a className="primary-button" href="#experiment">{simulationRunning ? 'Run controls' : 'Set up experiment'}</a></div>
      <WorkspaceDock mode="simulation" />
      <div className="telemetry"><span className={connected ? 'positive' : 'negative'}>{connected ? '● Connected' : '○ Disconnected'}</span><span>{simulationRunning ? 'Simulation running' : 'Simulation idle'}</span><span>Sim time <b>{marketData ? formatClock(marketData.timestamp) : '-'}</b></span><span>Step <b>{marketData?.step.toLocaleString() ?? '-'}</b></span><span>Clock <b><TerminalClock /> IST</b></span>{!connected && <button className="text-button" onClick={connect}>Reconnect ↗</button>}</div>
      <AlertBanner />
      {/* DraggableWidgetGrid and "Arrange the readout." were intentionally removed; market view is the post-launch focus. */}
      {/* Currency contract: marketData.market === 'NASDAQ' uses dollar formatting in the market panels. */}
      <section id="market" className="workspace-section" aria-labelledby="market-title">
        <div className="overview-grid"><div><PriceChart /></div>
          <aside className="market-reading"><span className="eyebrow">Reading the book</span><h2 id="market-title">{!marketData ? 'A market waiting to begin.' : marketData.liquidity_prediction?.warning_level === 'critical' ? 'Liquidity under stress.' : marketData.liquidity_prediction?.warning_level === 'warning' ? 'Pressure in the book.' : 'The current conditions.'}</h2><p>{marketData?.scenario.description ?? 'Choose a population and a scenario. Prices, orders, and risk signals will appear as the simulation advances.'}</p><dl><div><dt>Scenario phase</dt><dd>{marketData?.scenario.phase ?? '-'}</dd></div><div><dt>Liquidity health <InfoTip term="Liquidity health" /></dt><dd>{marketData?.liquidity_prediction ? `${marketData.liquidity_prediction.health_score.toFixed(1)} / 100` : 'Awaiting data'}</dd></div><div><dt>Warning level <InfoTip term="Warning level" /></dt><dd>{marketData?.liquidity_prediction?.warning_level ?? '-'}</dd></div><div><dt>Volatility <InfoTip term="Volatility" /></dt><dd>{marketData?.volatility.toFixed(4) ?? '-'}</dd></div></dl><a className="text-button" href="#signals">Inspect the signals ↗</a></aside></div>
        <div className="overview-lower"><DepthInspector /><TerminalEventPanel events={dashboard.events} connected={connected} simulationRunning={simulationRunning} /></div>
      </section>
      <section id="signals" className="workspace-section"><div className="view-intro"><span className="eyebrow">Signals</span><h2>Signals & evidence</h2><p>Liquidity condition and visible concentration, with their underlying measurements.</p></div><div className="signal-grid"><LiquidityGauge /><LargeOrderDetector /></div></section>
      <section id="agents" className="workspace-section"><div className="view-intro"><span className="eyebrow">Agents</span><h2>The market participants</h2><p>Positions, results, and current state for each simulated agent.</p></div><AgentMetricsPanel /></section>
      <section id="execution" className="workspace-section"><div className="view-intro"><span className="eyebrow">Execution</span><h2>Orders, fills & flow</h2><p>Trace the activity behind each change in the book.</p></div><TerminalActivityPanel activity={dashboard.agentActivity} connected={connected} simulationRunning={simulationRunning} /><div className="overview-lower"><TerminalTradeFlowPanel data={dashboard.tradeFlow} connected={connected} simulationRunning={simulationRunning} /><TerminalEventPanel events={dashboard.events} connected={connected} simulationRunning={simulationRunning} /></div></section>
      <section id="experiment" className="workspace-section"><div className="view-intro"><span className="eyebrow">Experiment</span><h2>Set the conditions</h2><p>Configure a population and observe how the market responds.</p></div><SandboxControlPanel onLaunched={focusMarket} /><section className="causal-state"><h2>CAUSAL MARKET STATE</h2><div>{causalCells.map(cell => <dl key={cell.label}><dt>{cell.label} <InfoTip term={cell.label} /></dt><dd>{cell.value}</dd></dl>)}</div></section></section>
    </main>
    <footer className="site-footer"><span>Sentinel / market microstructure research</span><span>{footerFeedLabel}</span></footer>
  </div>;
}
