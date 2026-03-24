'use client';

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
import PredictionPanel from '@/components/dashboard/PredictionPanel';
import { useMarketWebSocket } from '@/lib/websocket';
import { useDashboardData } from '@/lib/dashboard-data';

function formatSigned(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
}

export default function DashboardPage() {
  useMarketWebSocket();
  const dashboard = useDashboardData();

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
        tone:
          dashboard.metrics.realizedPnl >= 0
            ? ('positive' as const)
            : ('negative' as const),
      },
      {
        label: 'Unrealized PnL',
        value: `$${formatSigned(dashboard.metrics.unrealizedPnl)}`,
        hint: 'Mark-to-market',
        tone:
          dashboard.metrics.unrealizedPnl >= 0
            ? ('positive' as const)
            : ('negative' as const),
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
              <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-soft)]">
                SENTINEL Dashboard
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[var(--text-strong)] sm:text-4xl">
                Market Simulation and RL Progress Monitor
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-soft)]">
                Live monitoring for microstructure simulation, agent behavior tracing,
                and milestone visibility.
              </p>
            </div>
            <div className="rounded-2xl border border-[var(--line-soft)] bg-[var(--card-elevated)] px-4 py-3 text-sm">
              <p className="text-[11px] uppercase tracking-[0.12em] text-[var(--text-muted)]">Data Feed</p>
              <p
                className={`mt-1 font-semibold ${
                  dashboard.dataSource === 'live' ? 'text-[var(--mint)]' : 'text-[var(--gold)]'
                }`}
              >
                {dashboard.dataSource === 'live'
                  ? 'Live backend stream active'
                  : 'Mock stream fallback active'}
              </p>
              <p className="mt-1 text-xs text-[var(--text-soft)]">
                Mode: {dashboard.operatingMode === 'LIVE_SHADOW' ? 'LIVE_SHADOW (real market input)' : 'SIMULATION'}
              </p>
              <p className="mt-1 text-xs text-[var(--text-soft)]">
                {dashboard.operatingMode === 'LIVE_SHADOW'
                  ? (dashboard.liveMarketConnected ? 'Live Market Connected' : 'Using Mock Data')
                  : 'Live Market Feed Not Applicable'}
                {dashboard.operatingMode === 'LIVE_SHADOW' ? ` (${dashboard.liveMarketSource})` : ''}
              </p>
              <p className="mt-1 text-xs text-[var(--text-soft)]">
                Provider: {dashboard.liveMarketProvider}
                {dashboard.operatingMode === 'LIVE_SHADOW' ? ` | Fallback: ${dashboard.liveMarketFallback ? 'ON' : 'OFF'}` : ''}
              </p>
              {dashboard.operatingMode === 'LIVE_SHADOW' ? (
                <p className="mt-1 text-xs text-[var(--text-soft)]">
                  Health: {dashboard.liveMarketConnected ? 'healthy' : 'degraded'}
                  {dashboard.liveMarketTransport ? ` | Transport: ${dashboard.liveMarketTransport}` : ''}
                  {dashboard.liveMarketLatencyMs != null ? ` | Latency: ${dashboard.liveMarketLatencyMs.toFixed(0)} ms` : ''}
                  {dashboard.liveMarketStale ? ' | Stale: YES' : ' | Stale: NO'}
                </p>
              ) : null}
              {dashboard.operatingMode === 'LIVE_SHADOW' && dashboard.liveMarketMessage ? (
                <p className="mt-1 text-xs text-[var(--text-soft)]">
                  Feed message: {dashboard.liveMarketMessage}
                </p>
              ) : null}
              {dashboard.stale ? (
                <p className="mt-1 text-xs text-[var(--gold)]">Data appears stale. Waiting for new updates.</p>
              ) : null}
              {dashboard.error ? (
                <p className="mt-1 text-xs text-[var(--rose)]">{dashboard.error}</p>
              ) : null}
            </div>
          </div>
        </header>

        <ProjectOverviewPanel overview={dashboard.projectOverview} />

        {dashboard.loading ? (
          <section className="sentinel-card">
            <p className="text-sm text-[var(--text-soft)]">Loading live simulation feed...</p>
          </section>
        ) : null}

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

        <PredictionPanel prediction={dashboard.prediction} mode={dashboard.operatingMode} />

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
  );
}
