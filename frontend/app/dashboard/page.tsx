'use client';

<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 4435196 (Ani Here)
import { useMemo } from 'react';
import MetricCard from '@/components/dashboard/MetricCard';
import ProjectOverviewPanel from '@/components/dashboard/ProjectOverviewPanel';
import MilestoneTracker from '@/components/dashboard/MilestoneTracker';
import PriceSpreadChart from '@/components/dashboard/PriceSpreadChart';
import SeriesChartPanel from '@/components/dashboard/SeriesChartPanel';
import TradeFlowChart from '@/components/dashboard/TradeFlowChart';
import DepthHeatmapPanel from '@/components/dashboard/DepthHeatmapPanel';
import AgentActivityPanel from '@/components/dashboard/AgentActivityPanel';
import EventLogPanel from '@/components/dashboard/EventLogPanel';
import { useMarketWebSocket } from '@/lib/websocket';
import { useSimulationDashboardData } from '@/lib/mock-simulation';

function formatSigned(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
}

export default function DashboardPage() {
  useMarketWebSocket();
  const dashboard = useSimulationDashboardData();

  const metrics = useMemo(
    () => [
      {
        label: 'Mid Price',
        value: `$${dashboard.metrics.midPrice.toFixed(3)}`,
        hint: 'Real-time microprice estimate',
        tone: 'accent' as const,
      },
      {
        label: 'Best Bid / Best Ask',
        value: `${dashboard.metrics.bestBid.toFixed(3)} / ${dashboard.metrics.bestAsk.toFixed(3)}`,
        hint: 'Top of book',
      },
      {
        label: 'Spread',
        value: dashboard.metrics.spread.toFixed(4),
        hint: 'Inside market spread',
      },
      {
        label: 'LOB Imbalance',
        value: dashboard.metrics.orderBookImbalance.toFixed(3),
        hint: 'Bid vs ask pressure',
        tone:
          dashboard.metrics.orderBookImbalance > 0
            ? ('positive' as const)
            : ('negative' as const),
      },
      {
        label: 'Inventory',
        value: `${dashboard.metrics.inventory}`,
        hint: 'Net simulated position',
      },
      {
        label: 'Realized PnL',
        value: `$${formatSigned(dashboard.metrics.realizedPnl)}`,
        hint: 'Closed execution gains',
        tone: dashboard.metrics.realizedPnl >= 0 ? ('positive' as const) : ('negative' as const),
      },
      {
        label: 'Unrealized PnL',
        value: `$${formatSigned(dashboard.metrics.unrealizedPnl)}`,
        hint: 'Mark-to-market',
        tone: dashboard.metrics.unrealizedPnl >= 0 ? ('positive' as const) : ('negative' as const),
      },
      {
        label: 'Cumulative Reward',
        value: dashboard.metrics.cumulativeReward.toFixed(3),
        hint: 'RL objective trajectory',
        tone: 'accent' as const,
      },
    ],
    [dashboard.metrics],
  );

  return (
    <main className="min-h-screen bg-[var(--bg-main)] px-4 py-6 sm:px-6 lg:px-10">
      <div className="mx-auto w-full max-w-[1600px] space-y-6">
        <header className="sentinel-card relative overflow-hidden">
          <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-[radial-gradient(circle_at_center,rgba(86,166,255,0.3),transparent_70%)]" />
          <div className="pointer-events-none absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-[radial-gradient(circle_at_center,rgba(98,213,164,0.26),transparent_70%)]" />
          <div className="relative flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-soft)]">SENTINEL Dashboard</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[var(--text-strong)] sm:text-4xl">
                Market Simulation and RL Progress Monitor
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-soft)]">
                A presentation-ready research interface for microstructure simulation, agent behavior tracing, and milestone visibility.
              </p>
            </div>
            <div className="rounded-2xl border border-[var(--line-soft)] bg-[var(--card-elevated)] px-4 py-3 text-sm">
              <p className="text-[11px] uppercase tracking-[0.12em] text-[var(--text-muted)]">Data Feed</p>
              <p className={`mt-1 font-semibold ${dashboard.connected ? 'text-[var(--mint)]' : 'text-[var(--gold)]'}`}>
                {dashboard.connected ? 'Live backend stream connected' : 'Running simulated demo stream'}
              </p>
            </div>
          </div>
        </header>

        <ProjectOverviewPanel overview={dashboard.projectOverview} />

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard
              key={metric.label}
              label={metric.label}
              value={metric.value}
              hint={metric.hint}
              tone={metric.tone}
            />
          ))}
        </section>

        <section className="grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-7">
            <PriceSpreadChart data={dashboard.priceSeries} />
          </div>
          <div className="xl:col-span-5">
            <MilestoneTracker milestones={dashboard.milestones} />
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
          <SeriesChartPanel
            title="Spread Trend"
            subtitle="Stability and liquidity pressure"
            data={dashboard.spreadSeries}
            color="#ffcc70"
            valueFormatter={(value) => value.toFixed(4)}
            chartType="area"
          />
          <SeriesChartPanel
            title="Inventory Path"
            subtitle="Position exposure over time"
            data={dashboard.inventorySeries}
            color="#6fc4ff"
            valueFormatter={(value) => value.toFixed(0)}
          />
          <SeriesChartPanel
            title="Reward Curve"
            subtitle="Cumulative reward trajectory"
            data={dashboard.rewardSeries}
            color="#62d5a4"
            valueFormatter={(value) => value.toFixed(3)}
          />
          <DepthHeatmapPanel levels={dashboard.depthHeatmap} />
        </section>

        <section className="grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-7">
            <AgentActivityPanel activity={dashboard.agentActivity} />
          </div>
          <div className="xl:col-span-5 space-y-4">
            <TradeFlowChart data={dashboard.tradeFlow} />
            <EventLogPanel events={dashboard.events} />
          </div>
        </section>
      </div>
    </main>
<<<<<<< HEAD
=======
import React, { useState, useEffect } from 'react';
import { useMarketWebSocket } from '@/lib/websocket';
import { useMarketStore } from '@/store/market-store';
import { api } from '@/lib/api-client';
import PriceChart from '@/components/PriceChart';
import OrderBookHeatmap from '@/components/OrderBookHeatmap';
import LiquidityGauge from '@/components/LiquidityGauge';
import LargeOrderDetector from '@/components/LargeOrderDetector';
import AgentMetricsPanel from '@/components/AgentMetricsPanel';
import AlertBanner from '@/components/AlertBanner';

export default function DashboardPage() {
  useMarketWebSocket();

  const connected = useMarketStore((s) => s.connected);
  const marketData = useMarketStore((s) => s.marketData);
  const simulationRunning = useMarketStore((s) => s.simulationRunning);
  const setSimulationRunning = useMarketStore((s) => s.setSimulationRunning);
  const simulationMode = useMarketStore((s) => s.simulationMode);

  const [currentTime, setCurrentTime] = useState<string>('');

  useEffect(() => {
    setCurrentTime(new Date().toLocaleTimeString());
    const timer = setInterval(() => setCurrentTime(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(timer);
  }, []);

  const handleStartStop = async () => {
    try {
      if (simulationRunning) {
        await api.stopSimulation();
        setSimulationRunning(false);
      } else {
        await api.startSimulation();
        setSimulationRunning(true);
      }
    } catch (error) {
      console.error('Simulation control error:', error);
    }
  };

  const handleModeToggle = async () => {
    const newMode = simulationMode === 'SANDBOX' ? 'LIVE_SHADOW' : 'SANDBOX';
    try {
      await api.setSimulationMode(newMode);
    } catch (error) {
      console.error('Failed to change mode:', error);
    }
  };

  const formatTimestamp = (ts: number) => {
    const h = Math.floor(ts / 3600);
    const m = Math.floor((ts % 3600) / 60);
    const s = Math.floor(ts % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-black text-white font-mono">
      {/* ── Alert Banner ─── */}
      <AlertBanner />

      {/* ── Top Header Bar ─── */}
      <header className="border-b border-gray-800 px-4 py-2">
        <div className="flex items-center justify-between">
          {/* Left: Logo + Title */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-amber-400 rotate-45" />
              <span className="text-sm font-bold tracking-widest text-amber-400">
                SENTINEL
              </span>
            </div>
            <span className="text-xs text-gray-600 hidden sm:inline">
              SMART EARLY-WARNING NETWORK FOR TRADING
            </span>
          </div>

          {/* Center: Market Info */}
          <div className="flex items-center gap-4 text-xs">
            {marketData && (
              <>
                <span className="text-gray-500">
                  SIM TIME:{' '}
                  <span className="text-gray-300">
                    {formatTimestamp(marketData.timestamp)}
                  </span>
                </span>
                <span className="text-gray-500">
                  STEP:{' '}
                  <span className="text-gray-300">
                    {marketData.step.toLocaleString()}
                  </span>
                </span>
              </>
            )}
          </div>

          {/* Right: Connection + Controls */}
          <div className="flex items-center gap-3">
            {/* Connection status */}
            <div className="flex items-center gap-1.5 text-xs">
              <span
                className={connected ? 'blink' : ''}
                style={{ color: connected ? '#00ff41' : '#ff0040' }}
              >
                ●
              </span>
              <span className="text-gray-500">
                {connected ? 'CONNECTED' : 'DISCONNECTED'}
              </span>
            </div>

            {/* Mode toggle button */}
            <button
              onClick={handleModeToggle}
              className="px-3 py-1 text-xs font-mono font-bold border transition-all duration-200"
              style={{
                borderColor: simulationMode === 'SANDBOX' ? '#00ff41' : '#ffb000',
                color: simulationMode === 'SANDBOX' ? '#00ff41' : '#ffb000',
                backgroundColor: simulationMode === 'SANDBOX'
                  ? 'rgba(0, 255, 65, 0.1)'
                  : 'rgba(255, 176, 0, 0.1)',
              }}
            >
              {simulationMode === 'SANDBOX' ? 'MODE: SANDBOX' : 'MODE: LIVE'}
            </button>

            {/* Sim control button */}
            <button
              onClick={handleStartStop}
              className="px-3 py-1 text-xs font-mono font-bold border transition-all duration-200"
              style={{
                borderColor: simulationRunning ? '#ff0040' : '#00ff41',
                color: simulationRunning ? '#ff0040' : '#00ff41',
                backgroundColor: simulationRunning
                  ? 'rgba(255, 0, 64, 0.1)'
                  : 'rgba(0, 255, 65, 0.1)',
              }}
            >
              {simulationRunning ? '■ STOP' : '▶ START'}
            </button>
          </div>
        </div>
      </header>

      {/* ── Main Grid ─── */}
      <main className="p-2 grid grid-cols-12 gap-2 min-h-[calc(100vh-44px)]">
        {/* Top Row: Liquidity Gauge + Large Order Detector */}
        <div className="col-span-12 lg:col-span-3">
          <LiquidityGauge />
        </div>
        <div className="col-span-12 lg:col-span-3">
          <LargeOrderDetector />
        </div>
        <div className="col-span-12 lg:col-span-6">
          <PriceChart />
        </div>

        {/* Bottom Row: Order Book + Agent Metrics */}
        <div className="col-span-12 lg:col-span-4">
          <OrderBookHeatmap />
        </div>
        <div className="col-span-12 lg:col-span-8">
          <AgentMetricsPanel />
        </div>
      </main>

      {/* ── Status Bar ─── */}
      <footer className="fixed bottom-0 left-0 right-0 border-t border-gray-800 bg-black px-4 py-1 flex justify-between text-xs font-mono text-gray-600 z-50">
        <span>SENTINEL v2.0</span>
        <span>
          {marketData
            ? `$${marketData.price.toFixed(2)} | SPR ${marketData.spread.toFixed(4)} | DEPTH ${marketData.depth.toLocaleString()} | VOL ${marketData.volatility.toFixed(4)}`
            : 'AWAITING DATA...'}
        </span>
        <span>{currentTime}</span>
      </footer>
    </div>
>>>>>>> upstream/main
=======
>>>>>>> 4435196 (Ani Here)
  );
}
