'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import AppHeader from '@/components/ui/AppHeader';
import CandleChart from '@/components/ui/CandleChart';
import { LEVEL_COLOR, bps, duration, groupByType, int, median, num, pct, sessionClock, signed } from '@/lib/format';
import { aggregateCandles } from '@/lib/candles';
import { api } from '@/lib/api-client';
import { loadRunMeta } from '@/lib/run-meta';
import type { SimulationReport } from '@/types/api';

const MAX_CANDLES = 120;

const TERMS: Array<[string, string]> = [
  ['Spread (bps)', 'Best ask minus best bid, divided by the mid price, in basis points (1 bp = 0.01%).'],
  ['Visible depth', 'Total resting quantity on the book across the displayed levels.'],
  ['Imbalance', '(bid depth − ask depth) / (bid depth + ask depth). Negative means a sell-heavy book.'],
  ['Liquidity stress', 'Score from 0 to 1 from spread, depth, volatility and flow against their trailing baselines. Health is 1 − stress.'],
  ['large_level', 'A visible price level far larger than the median level, with its share of that side of the book.'],
  ['Match rate', 'Orders that traded at least once, as a share of orders submitted.'],
  ['VWAP', 'Volume-weighted average price of the recorded trades.'],
  ['Marked PnL', 'Realized PnL plus open positions valued at the final mid price.'],
];

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

const cell = (value: unknown) => (typeof value === 'number' ? value : Number(value));

function Card({ id, title, aside, children, className = '' }: { id: string; title: string; aside?: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-labelledby={id} className={`flex min-w-0 flex-col gap-2.5 rounded-panel bg-ink-2 px-[18px] py-4 ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={id} className="m-0 text-[15px] font-semibold">{title}</h2>
        {aside ? <span className="text-xs text-fg-muted">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

function Pairs({ rows }: { rows: Array<[string, string]> }) {
  return (
    <dl className="m-0 grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-[13px]">
      {rows.map(([label, value]) => (
        <div key={label} className="contents"><dt className="text-fg-muted">{label}</dt><dd className="m-0 text-right font-semibold">{value}</dd></div>
      ))}
    </dl>
  );
}

export default function SessionReportPage() {
  const [report, setReport] = useState<SimulationReport | null>(null);
  const [error, setError] = useState('');
  const [pdfBusy, setPdfBusy] = useState(false);

  useEffect(() => {
    api.getSimulationReport().then(setReport).catch((caught: Error) => setError(caught.message));
  }, []);

  const derived = useMemo(() => {
    if (!report) return null;
    const path = report.price_path;
    const span = Math.max(1, path.at(-1)?.timestamp ?? 1);
    const interval = Math.max(5, Math.ceil(span / MAX_CANDLES / 5) * 5);
    const candles = aggregateCandles(path.map((p) => ({ receivedAt: p.timestamp * 1000, price: p.price })), interval * 1000);
    const spreadBps = path.map((p) => bps(p.spread, p.price) ?? 0);
    const trades = report.order_flow.trades;
    const tradedVolume = trades.reduce((total, t) => total + t.quantity, 0);
    const vwap = tradedVolume ? trades.reduce((total, t) => total + t.price * t.quantity, 0) / tradedVolume : null;
    const stressRows = report.warning_timeline.filter((w) => w.detector === 'liquidity_stress');
    const peak = stressRows.reduce<(typeof stressRows)[number] | null>((best, row) => (!best || cell(row.stress_score) > cell(best.stress_score) ? row : best), null);
    const warnWindows: Array<[number, number]> = [];
    stressRows.forEach((row, index) => {
      if (row.warning_level !== 'warning' && row.warning_level !== 'critical') return;
      const start = cell(row.timestamp);
      const next = stressRows[index + 1];
      warnWindows.push([start * 1000, (next ? cell(next.timestamp) : start + interval) * 1000]);
    });
    return {
      path, interval, candles, spreadBps, tradedVolume, vwap, peak, warnWindows,
      medianSpread: median(spreadBps),
      medianDepth: median(path.map((p) => p.depth)),
      maxSpreadIndex: spreadBps.reduce((best, v, i) => (v > spreadBps[best] ? i : best), 0),
      minDepthIndex: path.reduce((best, p, i) => (p.depth < path[best].depth ? i : best), 0),
      groups: groupByType(report.agent_metrics),
    };
  }, [report]);

  const downloadPdf = async () => {
    setPdfBusy(true);
    try {
      download(await api.downloadSimulationReportPdf(), `sentinel-session-${report?.run_config.seed ?? 'unseeded'}.pdf`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'PDF download failed.');
    } finally {
      setPdfBusy(false);
    }
  };

  const header = (
    <AppHeader
      context={<Link href="/dashboard" className="inline-flex min-h-10 items-center text-fg-muted no-underline">← Dashboard</Link>}
      actions={report ? <>
        <button type="button" className="btn" onClick={() => download(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }), `sentinel-session-${report.run_config.seed ?? 'unseeded'}.json`)}>Download JSON</button>
        <button type="button" className="btn btn-light" onClick={downloadPdf} disabled={pdfBusy}>{pdfBusy ? 'Preparing PDF…' : 'Download PDF'}</button>
      </> : null}
    />
  );

  if (!report || !derived) {
    return (
      <div className="min-h-screen bg-ink text-fg">
        {header}
        <main className="mx-auto max-w-[1200px] px-4 py-16 sm:px-6">
          {error ? (
            <div className="flex max-w-xl flex-col items-start gap-3 rounded-panel bg-ink-2 p-6">
              <h1 className="m-0 font-display text-2xl font-semibold">No session report yet.</h1>
              <p className="m-0 text-fg-muted">Stop a running session, or let one reach the close, to freeze its report here.</p>
              <Link href="/dashboard" className="btn">Back to the dashboard</Link>
            </div>
          ) : <p role="status" className="m-0 text-fg-muted">Assembling the session record…</p>}
        </main>
      </div>
    );
  }

  const { run_config: run, order_flow: flow } = report;
  // The backend stores 'custom' as the preset; recover the launched preset when this is that run.
  const launched = loadRunMeta();
  const preset = run.preset === 'custom' && launched && launched.seed === run.seed ? launched.preset : run.preset;
  const { path, peak } = derived;
  const open = path[0]?.price ?? run.initial_price;
  const close = path.at(-1)?.price ?? open;
  const change = open ? close / open - 1 : 0;
  const maxSpread = derived.spreadBps[derived.maxSpreadIndex] ?? 0;
  const minDepth = path[derived.minDepthIndex]?.depth ?? 0;
  const maxPnl = Math.max(1, ...derived.groups.map((g) => Math.abs(g.total)));
  const detectors = report.warning_timeline.slice(0, 300);
  const largeFlags = report.warning_timeline.filter((w) => w.detector === 'visible_liquidity');

  const summary = [
    `The mid moved ${signed(change * 100, 2, '%')} from ${num(open, 3)} to ${num(close, 3)} over ${duration(run.elapsed_seconds)} of simulated trading.`,
    peak
      ? `Liquidity stress peaked at ${num(cell(peak.stress_score))} (${String(peak.warning_level)}) at ${sessionClock(cell(peak.timestamp))}, across ${report.warning_timeline.length} detector transitions.`
      : 'The liquidity detector never left the safe band.',
    `The widest spread was ${num(maxSpread, 1)} bps${derived.medianSpread ? ` (${num(maxSpread / derived.medianSpread, 1)}× the session median)` : ''} at ${sessionClock(path[derived.maxSpreadIndex]?.timestamp)}, and visible depth bottomed at ${int(minDepth)}${derived.medianDepth ? ` (${pct(minDepth / derived.medianDepth)} of median)` : ''}.`,
    largeFlags.length ? `${largeFlags.length} large visible level${largeFlags.length === 1 ? ' was' : 's were'} flagged.` : '',
    `${int(flow.summary.fills)} trades from ${int(flow.summary.submitted)} orders, a ${num(flow.summary.match_rate, 0)}% match rate.`,
  ].filter(Boolean).join(' ');

  return (
    <div className="min-h-screen bg-ink text-fg [font-variant-numeric:tabular-nums]">
      <div className="no-print">{header}</div>
      <main className="mx-auto flex max-w-[1200px] flex-col gap-3.5 px-4 pb-16 pt-7 sm:px-6">
        <section className="flex flex-col gap-1.5 pb-1.5">
          <span className="text-xs tracking-[0.04em] text-fg-muted">SENTINEL · SIMULATION SESSION RECORD · {run.venue}</span>
          <h1 className="m-0 font-display text-[36px] font-semibold leading-tight tracking-[-0.02em]">{run.scenario.replaceAll('_', ' ')}, {preset.replaceAll('_', ' ')} population</h1>
        </section>

        <section aria-label="Configuration" className="grid gap-px overflow-hidden rounded-panel bg-line" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 140px), 1fr))' }}>
          {[
            ['Scenario', run.scenario],
            ['Preset', `${preset} · ${run.agent_count} agents`],
            ['Seed', run.seed == null ? 'random' : String(run.seed)],
            ['Latency', run.latency_mode.toLowerCase()],
            ['Oracle', run.informed_access ? 'on' : 'off'],
            ['Elapsed', duration(run.elapsed_seconds)],
            ['Generated', new Date(report.generated_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })],
          ].map(([label, value]) => (
            <div key={label} className="min-w-0 bg-ink-2 px-3.5 py-3"><span className="block text-xs text-fg-muted">{label}</span><span className="block truncate font-semibold">{value}</span></div>
          ))}
        </section>

        <section aria-labelledby="summary" className="flex flex-col gap-2.5 rounded-panel bg-paper px-6 py-[22px] text-ink">
          <h2 id="summary" className="m-0 text-[15px] font-bold">Executive summary</h2>
          <p className="m-0 max-w-[900px] text-base">{summary}</p>
        </section>

        <section aria-label="Key measurements" className="grid gap-px overflow-hidden rounded-panel bg-line" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 170px), 1fr))' }}>
          {[
            ['Close', num(close, 3), `from ${num(open, 3)} · ${signed(change * 100, 2, '%')}`],
            ['Peak stress', peak ? num(cell(peak.stress_score)) : '—', peak ? `${String(peak.warning_level)}, ${sessionClock(cell(peak.timestamp))}` : 'no warning raised'],
            ['Max spread', `${num(maxSpread, 1)} bps`, derived.medianSpread ? `${num(maxSpread / derived.medianSpread, 1)}× session median` : ''],
            ['Min visible depth', int(minDepth), derived.medianDepth ? `${pct(minDepth / derived.medianDepth)} of median` : ''],
            ['VWAP', num(derived.vwap, 3), `${int(derived.tradedVolume)} shares traded`],
            ['Mean volatility', `${num((report.validation_metrics.volatility_mean ?? 0) * 100, 1)}%`, 'realized, annualized'],
          ].map(([label, value, note]) => (
            <div key={label} className="flex min-w-0 flex-col gap-0.5 bg-ink-2 px-4 py-3.5">
              <span className="text-xs text-fg-muted">{label}</span>
              <span className="truncate font-display text-2xl font-semibold">{value}</span>
              <span className="truncate text-xs text-fg-muted">{note}</span>
            </div>
          ))}
        </section>

        <Card id="tape" title="Candle tape" aside={`${derived.interval}-second OHLC · shaded where stress reached warning`}>
          {derived.candles.length ? (
            <>
              <CandleChart candles={derived.candles} shade={derived.warnWindows} height={260} showVolume={false}
                timeLabel={(ms) => sessionClock(ms / 1000)} label={`${derived.interval}-second candles for the whole run`} />
              <Sparkline label="spread bps" values={derived.spreadBps} color="var(--accent)" />
              <Sparkline label="visible depth" values={path.map((p) => p.depth)} color="var(--fg-2)" />
            </>
          ) : <p className="m-0 text-fg-muted">No price observations were recorded.</p>}
        </Card>

        <div className="flex flex-wrap items-stretch gap-3.5">
          <Card id="detectors" title="Detector record" aside={report.warning_timeline.length > detectors.length ? `first ${detectors.length} of ${report.warning_timeline.length}` : `${detectors.length} transitions`} className="flex-[1_1_520px]">
            {detectors.length ? (
              <div className="max-h-[420px] overflow-auto">
                <table className="data-table min-w-[420px]">
                  <thead><tr><th scope="col">Time</th><th scope="col">Detector</th><th scope="col">Transition</th><th scope="col" className="num">Value</th></tr></thead>
                  <tbody>
                    {detectors.map((row, index) => {
                      const stress = row.detector === 'liquidity_stress';
                      const level = String(row.warning_level ?? '');
                      return (
                        <tr key={`${row.timestamp}-${index}`}>
                          <td className="text-fg-muted">{sessionClock(cell(row.timestamp), true)}</td>
                          <td>{stress ? 'liquidity_stress' : 'large_order'}</td>
                          <td className="font-semibold" style={{ color: stress ? LEVEL_COLOR[level] : 'var(--accent)' }}>
                            {stress ? `→ ${level}` : `flag ${String(row.side ?? '').toUpperCase()} ${int(cell(row.estimated_size))}`}
                          </td>
                          <td className="num">{stress ? num(cell(row.stress_score)) : num(cell(row.confidence))}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : <p className="m-0 text-[13px] text-fg-muted">No detector crossed a warning threshold during this run.</p>}
          </Card>
          <Card id="accounting" title="Execution accounting" className="flex-[1_1_380px]">
            <Pairs rows={[
              ['Orders submitted', int(flow.submitted_orders)],
              ['Fills', int(flow.summary.fills)],
              ['Cancel requests', int(flow.cancel_requests)],
              ['Accepted cancels', int(flow.accepted_cancels)],
              ['Expired / terminal cancels', int(flow.terminal_cancels)],
              ['Match rate', `${num(flow.summary.match_rate, 0)}%`],
              ['Traded volume', int(derived.tradedVolume)],
              ['Mean impact', `${num(report.validation_metrics.impact_bps_mean, 2)} bps`],
              ['Mean slippage', `${num(report.validation_metrics.slippage_bps_mean, 2)} bps`],
              ['Agents halted', int(derived.groups.reduce((total, g) => total + g.halted, 0))],
            ]} />
          </Card>
        </div>

        <section aria-labelledby="outcomes" className="overflow-hidden rounded-panel bg-ink-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-[18px] py-3.5">
            <h2 id="outcomes" className="m-0 text-[15px] font-semibold">Participant outcomes</h2>
            <span className="text-xs text-fg-muted">grouped by agent type · PnL marked to final mid {num(close, 3)}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="data-table min-w-[780px]">
              <thead><tr><th scope="col">Agent type</th><th scope="col" className="num">Count</th><th scope="col" className="num">Trades</th><th scope="col" className="num">Net position</th><th scope="col" className="num">Halted</th><th scope="col" className="w-[200px]">PnL distribution</th><th scope="col" className="num">Total PnL</th></tr></thead>
              <tbody>
                {derived.groups.map((g) => (
                  <tr key={g.type}>
                    <td className="font-semibold">{g.type}</td>
                    <td className="num text-fg-muted">{g.count}</td>
                    <td className="num">{int(g.trades)}</td>
                    <td className="num">{signed(g.position, 0)}</td>
                    <td className="num">{g.halted ? g.halted : 'no'}</td>
                    <td>
                      <span className="grid h-2 grid-cols-2" aria-hidden="true">
                        <span className="flex justify-end border-r border-line-dim"><span className="h-2 rounded-l bg-accent" style={{ width: `${(Math.max(0, -g.total) / maxPnl) * 100}%` }} /></span>
                        <span className="flex"><span className="h-2 rounded-r bg-fg" style={{ width: `${(Math.max(0, g.total) / maxPnl) * 100}%` }} /></span>
                      </span>
                    </td>
                    <td className="num font-bold" style={{ color: g.total < 0 ? 'var(--accent)' : 'var(--fg)' }}>{signed(g.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="flex flex-wrap items-stretch gap-3.5">
          <Card id="coverage" title="Data coverage" className="flex-[1_1_380px]">
            <Pairs rows={[
              ['Simulation steps', int(run.steps)],
              ['Elapsed (simulated)', duration(run.elapsed_seconds)],
              ['Price samples', int(path.length)],
              [`${derived.interval} s candles`, int(derived.candles.length)],
              ['Recorded trades', int(flow.trades.length)],
              ['Exchange events', int(report.events.length)],
              ['Detector transitions', int(report.warning_timeline.length)],
            ]} />
            <p className="m-0 text-xs text-fg-muted">A short run should not be treated as a stable estimate.</p>
          </Card>
          <Card id="method" title="Method and limitations" className="flex-[2_1_560px]">
            <p className="m-0 text-fg-2">Values are calculated from the simulator&apos;s recorded state path and final execution counters. Agent PnL is marked to the final simulated price. VWAP uses the recorded trades.</p>
            <p className="m-0 text-fg-2">This is one synthetic run under the listed seed, scenario, population and latency assumptions. It is not evidence of real-market profitability or a forecast of future prices. Repeat with other seeds before drawing conclusions.</p>
          </Card>
        </div>

        <Card id="terms" title="Terms used in this report">
          <dl className="m-0 grid gap-x-6 gap-y-3 text-[13px]" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))' }}>
            {TERMS.map(([term, meaning]) => (
              <div key={term}><dt className="font-semibold">{term}</dt><dd className="m-0 mt-0.5 text-fg-muted">{meaning}</dd></div>
            ))}
          </dl>
        </Card>
      </main>
    </div>
  );
}

/** A labelled one-line series under the candles, downsampled to ~300 points. */
function Sparkline({ label, values, color }: { label: string; values: number[]; color: string }) {
  const stride = Math.max(1, Math.ceil(values.length / 300));
  const points = values.filter((_, i) => i % stride === 0);
  const lo = Math.min(...points);
  const hi = Math.max(...points);
  const line = points.map((v, i) => `${((i / Math.max(1, points.length - 1)) * 1000).toFixed(1)},${(36 - ((v - lo) / Math.max(1e-9, hi - lo)) * 32).toFixed(1)}`).join(' ');
  return (
    <div className="flex items-center gap-3 border-t border-line pt-2">
      <span className="w-24 flex-none text-[11px] text-fg-muted">{label}<br />{num(lo, 1)}–{num(hi, 1)}</span>
      <svg viewBox="0 0 1000 40" preserveAspectRatio="none" className="h-10 min-w-0 flex-1" role="img" aria-label={`${label} over the run, from ${num(lo, 1)} to ${num(hi, 1)}`}>
        <polyline points={line} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}
