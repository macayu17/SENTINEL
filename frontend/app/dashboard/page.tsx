'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import ActivityPanel from '@/components/dashboard/ActivityPanel';
import FlowPanel from '@/components/dashboard/FlowPanel';
import OrderBookPanel from '@/components/dashboard/OrderBookPanel';
import StressPanel from '@/components/dashboard/StressPanel';
import AppHeader from '@/components/ui/AppHeader';
import CandleChart from '@/components/ui/CandleChart';
import Ticker from '@/components/ui/Ticker';
import { EmptyState, Panel, Segmented, Stat, StatGrid, StatusDot } from '@/components/ui/primitives';
import { api } from '@/lib/api-client';
import { estimatedVwap, flowBuckets, tapeCandles, tapeMedians, useSessionTape, warningWindows } from '@/lib/dashboard-data';
import { TICK, bookStats, bps, int, num, pct, sessionClock, signed } from '@/lib/format';
import { loadRunMeta, type RunMeta } from '@/lib/run-meta';
import { useMarketWebSocket } from '@/lib/websocket';
import { useMarketStore } from '@/store/market-store';

type Interval = '1' | '5' | '60';
const INTERVALS: Array<{ value: Interval; label: string }> = [
  { value: '1', label: '1s' },
  { value: '5', label: '5s' },
  { value: '60', label: '1m' },
];

function downloadJson(payload: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function DashboardPage() {
  const router = useRouter();
  const { connect } = useMarketWebSocket();
  const data = useMarketStore((s) => s.marketData);
  const connected = useMarketStore((s) => s.connected);
  const running = useMarketStore((s) => s.simulationRunning);
  const alerts = useMarketStore((s) => s.alerts);
  const dismissAlert = useMarketStore((s) => s.dismissAlert);
  const resetSimulationData = useMarketStore((s) => s.resetSimulationData);
  const setSimulationRunning = useMarketStore((s) => s.setSimulationRunning);
  const tape = useSessionTape();
  const [candleInterval, setCandleInterval] = useState<Interval>('5');
  const [meta, setMeta] = useState<RunMeta | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    setMeta(loadRunMeta());
    let cancelled = false;
    api.health()
      .then((health) => {
        if (cancelled) return;
        setSimulationRunning(health.simulation_active);
        if (!health.simulation_active) resetSimulationData();
      })
      .catch(() => undefined); // the socket state still drives the screen
    return () => { cancelled = true; };
  }, [resetSimulationData, setSimulationRunning]);

  const book = bookStats(data?.order_book);
  const medians = useMemo(() => tapeMedians(tape), [tape]);
  const vwap = useMemo(() => estimatedVwap(tape), [tape]);
  const candles = useMemo(() => tapeCandles(tape, Number(candleInterval)), [tape, candleInterval]);
  const shade = useMemo(() => warningWindows(tape).map(([a, b]) => [a * 1000, b * 1000] as [number, number]), [tape]);
  const buckets = useMemo(() => flowBuckets(tape), [tape]);
  const spreadBps = bps(data?.spread, data?.price);
  const change = data && tape[0] ? data.price / tape[0].price - 1 : null;
  const spreadRatio = spreadBps != null && medians.spreadBps ? spreadBps / medians.spreadBps : null;
  const bidShare = medians.bidDepth ? book.bidDepth / medians.bidDepth : null;
  const askShare = medians.askDepth ? book.askDepth / medians.askDepth : null;
  const prediction = data?.liquidity_prediction;
  const detection = data?.large_order_detection;
  const agentCount = Object.keys(data?.agent_metrics ?? {}).length || meta?.agents;
  const alert = [...alerts].reverse().find((a) => !a.dismissed);
  const live = connected && running;

  const stop = async () => {
    setBusy(true);
    try {
      await api.stopSimulation();
      resetSimulationData();
      setSimulationRunning(false);
      router.push('/dashboard/session-report');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Stop failed.');
      setBusy(false);
    }
  };

  const exportRun = async () => {
    try {
      downloadJson(await api.exportSimulation(), `sentinel-run-${meta?.seed ?? 'unseeded'}.json`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Export failed.');
    }
  };

  const headerFacts = [
    { k: 'Scenario', v: data?.scenario.name ?? meta?.scenario },
    { k: 'Preset', v: meta ? `${meta.preset} · ${meta.agents}` : undefined },
    { k: 'Seed', v: meta?.seed ?? undefined },
    { k: 'Latency', v: data?.latency_mode?.toLowerCase() ?? meta?.latency },
    { k: 'Phase', v: data?.session_phase?.toLowerCase() },
    { k: 'Time', v: data ? sessionClock(data.timestamp) : undefined },
    { k: 'Step', v: data ? int(data.step) : undefined },
  ].filter((fact) => fact.v !== undefined && fact.v !== null);

  const tickerItems = data ? [
    { label: 'SIM', value: `${num(data.price, 3)} ${change == null ? '' : signed(change * 100, 2, '%')}` },
    { label: 'SPREAD', value: `${num(spreadBps, 1)} bps` },
    { label: 'STRESS', value: prediction ? `${num(prediction.stress_score)} ${prediction.warning_level.toUpperCase()}` : '—' },
    { label: 'DEPTH', value: `${int(book.bidDepth)} / ${int(book.askDepth)}` },
    { label: 'IMBALANCE', value: signed(book.imbalance) },
    { label: 'VWAP', value: num(vwap, 3) },
    ...(detection ? [{ label: 'LARGE LEVEL', value: `${detection.side.toUpperCase()} ${int(detection.estimated_size)} @ ${num(detection.price, 2)}` }] : []),
    { label: 'FILLS', value: int(data.order_flow?.fills) },
    { label: 'MATCH RATE', value: `${num(data.order_flow?.match_rate, 0)}%` },
    ...(agentCount ? [{ label: 'AGENTS', value: String(agentCount) }] : []),
  ] : [];

  return (
    <div className="min-h-screen bg-ink text-fg [font-variant-numeric:tabular-nums]">
      <AppHeader
        wide
        context={headerFacts.length ? (
          <dl className="m-0 flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
            {headerFacts.map((fact) => (
              <div key={fact.k} className="flex gap-1.5"><dt className="text-fg-muted">{fact.k}</dt><dd className="m-0 font-semibold">{fact.v}</dd></div>
            ))}
          </dl>
        ) : null}
        actions={<>
          <StatusDot live={live} label={!connected ? 'Offline' : running ? 'Live' : 'Idle'} />
          {!connected && <button type="button" className="btn" onClick={connect}>Reconnect</button>}
          <button type="button" className="btn" onClick={stop} disabled={busy || !running}>Stop &amp; save report</button>
          <button type="button" className="btn" onClick={exportRun} disabled={!running}>Export JSON</button>
          <Link href="/start" className="btn btn-light">New session</Link>
        </>}
      >
        {tickerItems.length ? <Ticker items={tickerItems} /> : null}
      </AppHeader>

      {alert && (
        <div role="alert" className="border-b border-alert-line bg-alert-bg">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
            <span>
              <strong className="font-bold text-accent">{alert.level.toUpperCase()} · liquidity stress, raised at {sessionClock(alert.timestamp, true)}.</strong>{' '}
              <span className="text-fg-2">
                Now: stress {num(prediction?.stress_score)} ({prediction?.warning_level ?? '—'})
                {prediction?.features.depth_ratio != null && `, depth at ${pct(prediction.features.depth_ratio)} of its baseline`}
                {spreadRatio != null && `, spread ${num(spreadRatio, 1)}× median`}, order book imbalance {signed(book.imbalance)}.
              </span>
            </span>
            <button type="button" onClick={() => dismissAlert(alert.id)} className="btn min-h-[34px] border border-alert-line bg-transparent text-alert-fg">Acknowledge</button>
          </div>
        </div>
      )}

      <main className="flex flex-col gap-3 px-4 pb-10 pt-4 sm:px-6">
        {message && <p role="status" className="m-0 rounded-[10px] bg-ink-2 px-4 py-2 text-[13px] text-alert-fg">{message}</p>}

        {!data && (
          <section className="flex flex-col items-start gap-3 rounded-panel bg-ink-2 px-[18px] py-6">
            <h1 className="m-0 font-display text-2xl font-semibold">{connected ? 'No session running.' : 'Backend offline.'}</h1>
            <p className="m-0 max-w-xl text-fg-muted">
              {connected
                ? 'Configure an agent population and a scenario to start streaming candles, the order book and liquidity signals.'
                : 'The dashboard reconnects to the simulator WebSocket automatically. Start the backend, then reconnect.'}
            </p>
            <Link href="/start" className="btn btn-accent">Configure a run</Link>
          </section>
        )}

        <StatGrid label="Market summary">
          <Stat label="Mid price" value={num(data?.price, 3)} note={change == null ? 'session' : `${signed(change * 100, 2, '%')} · session`} alert={(change ?? 0) < 0} />
          <Stat label="Spread" value={`${num(spreadBps, 1)} bps`} note={data ? `${int(data.spread / TICK)} tick${Math.round(data.spread / TICK) === 1 ? '' : 's'}${spreadRatio ? ` · ${num(spreadRatio, 1)}× median` : ''}` : undefined} alert={(spreadRatio ?? 0) > 1.5} />
          <Stat label="Bid depth" value={int(data ? book.bidDepth : null)} note={bidShare ? `${pct(bidShare)} of median` : undefined} alert={(bidShare ?? 1) < 0.6} />
          <Stat label="Ask depth" value={int(data ? book.askDepth : null)} note={askShare ? `${pct(askShare)} of median` : undefined} alert={(askShare ?? 1) < 0.6} />
          <Stat label="Imbalance" value={data ? signed(book.imbalance) : '—'} note={data ? (book.imbalance < -0.2 ? 'sell-heavy book' : book.imbalance > 0.2 ? 'buy-heavy book' : 'balanced book') : undefined} alert={Math.abs(book.imbalance) > 0.2} />
          <Stat label="Volatility" value={data ? `${num(data.volatility * 100, 1)}%` : '—'} note="realized, annualized" />
          <Stat label="VWAP" value={num(vwap, 3)} note="session · estimated" />
          <Stat label="Match rate" value={data?.order_flow ? `${num(data.order_flow.match_rate, 0)}%` : '—'} note={data?.order_flow ? `${int(data.order_flow.fills)} fills` : undefined} />
        </StatGrid>

        <div className="flex flex-wrap items-stretch gap-3">
          <Panel
            title="SIM · mid price"
            caption="OHLC candles · volume (est.) · VWAP (dashed)"
            actions={<Segmented label="Candle interval" role="tab" size="sm" options={INTERVALS} value={candleInterval} onChange={setCandleInterval} />}
            className="flex-[999_1_640px]"
          >
            {candles.length ? (
              <CandleChart
                candles={candles}
                shade={shade}
                showVwap
                timeLabel={(ms) => sessionClock(ms / 1000)}
                label={`Mid-price candles at ${INTERVALS.find((i) => i.value === candleInterval)?.label} with estimated volume and VWAP; shaded spans mark liquidity warnings`}
              />
            ) : <EmptyState>Candles appear with the first market updates.</EmptyState>}
          </Panel>
          <StressPanel prediction={prediction} detection={detection} />
        </div>

        <div className="flex flex-wrap items-stretch gap-3">
          <OrderBookPanel book={data?.order_book} mid={data?.price} spread={data?.spread} flagged={detection} />
          <FlowPanel data={data} buckets={buckets} />
        </div>

        <ActivityPanel data={data} />
      </main>
    </div>
  );
}
