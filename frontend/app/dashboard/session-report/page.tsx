'use client';

import { ArrowLeft, Download, Printer } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import ThemeToggle from '@/components/ThemeToggle';
import { api } from '@/lib/api-client';
import { aggregateCandles } from '@/lib/candles';
import type { SimulationReport } from '@/types/api';

const number = (value: number | null | undefined, digits = 2) =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'N/A';

const signed = (value: number, digits = 2, suffix = '') =>
  `${value >= 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`;

function humanize(value: string) {
  return value.replaceAll('_', ' ').toUpperCase();
}

function reportLabel(value: string) {
  return value.replaceAll('_', ' ');
}

function downloadReport(report: SimulationReport) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `sentinel-session-${report.run_config.seed ?? 'unseeded'}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function SessionReportPage() {
  const [report, setReport] = useState<SimulationReport | null>(null);
  const [error, setError] = useState('');
  const [pdfDownloading, setPdfDownloading] = useState(false);

  useEffect(() => {
    api.getSimulationReport().then(setReport).catch((caught: Error) => setError(caught.message));
  }, []);

  const chartData = useMemo(() => {
    if (!report) return [];
    const stride = Math.max(1, Math.ceil(report.price_path.length / 800));
    return report.price_path.filter((_, index) => index % stride === 0 || index === report.price_path.length - 1);
  }, [report]);

  const reportCandles = useMemo(() => {
    if (!report) return [];
    return aggregateCandles(
      report.price_path.map((point) => ({ receivedAt: point.timestamp * 1000, price: point.price })),
      5000,
    );
  }, [report]);

  const downloadPdf = async () => {
    setPdfDownloading(true);
    try {
      const blob = await api.downloadSimulationReportPdf();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `sentinel-simulation-report-${report?.run_config.seed ?? 'unseeded'}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'PDF download failed.');
    } finally {
      setPdfDownloading(false);
    }
  };

  if (error) {
    return (
      <main className="report-page min-h-screen w-full overflow-x-hidden bg-black p-6 text-gray-200">
        <a href="/dashboard" className="inline-flex items-center gap-2 text-xs text-gray-500 hover:text-white"><ArrowLeft size={14} /> DASHBOARD</a>
        <div className="mx-auto mt-24 w-full max-w-xl border border-red-950 bg-red-950/10 p-6">
          <div className="text-[10px] tracking-[0.16em] text-red-400">REPORT UNAVAILABLE</div>
          <p className="mt-3 text-sm leading-6 text-gray-400">Stop a running simulation to preserve its final session report.</p>
        </div>
      </main>
    );
  }

  if (!report) {
    return <main className="report-page min-h-screen bg-black p-8 font-mono text-xs tracking-[0.14em] text-gray-500">ASSEMBLING SESSION RECORD...</main>;
  }

  const path = report.price_path;
  const first = path[0];
  const last = path.at(-1);
  const startPrice = first?.price ?? report.run_config.initial_price;
  const finalPrice = last?.price ?? startPrice;
  const priceChange = startPrice ? ((finalPrice - startPrice) / startPrice) * 100 : 0;
  const peakSpread = Math.max(0, ...path.map((point) => point.spread));
  const minimumDepth = path.length ? Math.min(...path.map((point) => point.depth)) : 0;
  const maximumVolatility = Math.max(0, ...path.map((point) => point.volatility));
  const totalPnl = Object.values(report.agent_metrics).reduce((sum, agent) => sum + agent.total_pnl, 0);
  const warningRisk = Math.max(0, ...report.warning_timeline.map((warning) => {
    const value = warning.probability ?? warning.stress_score ?? 0;
    return typeof value === 'number' ? value : 0;
  }));

  const agents = Object.values(report.agent_metrics).reduce<Record<string, {
    count: number;
    trades: number;
    position: number;
    pnl: number;
    halted: number;
  }>>((grouped, agent) => {
    const row = grouped[agent.agent_type] ?? { count: 0, trades: 0, position: 0, pnl: 0, halted: 0 };
    row.count += 1;
    row.trades += agent.num_trades;
    row.position += agent.position;
    row.pnl += agent.total_pnl;
    row.halted += agent.halted ? 1 : 0;
    grouped[agent.agent_type] = row;
    return grouped;
  }, {});

  const eventCounts = report.events.reduce<Record<string, number>>((counts, event) => {
    const type = typeof event.type === 'string' ? event.type : 'unknown';
    counts[type] = (counts[type] ?? 0) + 1;
    return counts;
  }, {});

  const findings = [
    `The mid price moved ${signed(priceChange, 2, '%')} from ${number(startPrice)} to ${number(finalPrice)}.`,
    `Displayed depth reached a session low of ${minimumDepth.toLocaleString()} while the widest spread was ${number(peakSpread, 4)}.`,
    `${report.order_flow.summary.fills.toLocaleString()} trades followed ${report.order_flow.summary.submitted.toLocaleString()} submissions, a ${number(report.order_flow.summary.match_rate)}% match rate.`,
    report.warning_timeline.length
      ? `${report.warning_timeline.length} detector transition${report.warning_timeline.length === 1 ? '' : 's'} were recorded; peak reported risk was ${number(warningRisk * 100, 1)}%.`
      : 'No liquidity or concentrated-book warning transition was recorded.',
  ];

  const headline = [
    ['FINAL PRICE', `$${number(finalPrice)}`, signed(priceChange, 2, '%')],
    ['PEAK SPREAD', number(peakSpread, 4), `mean ${number(report.validation_metrics.spread_mean, 4)}`],
    ['MINIMUM DEPTH', minimumDepth.toLocaleString(), `${path.length.toLocaleString()} observations`],
    ['TRADES', report.order_flow.summary.fills.toLocaleString(), `${number(report.order_flow.summary.match_rate)}% matched`],
    ['TOTAL PNL', signed(totalPnl, 2), `${Object.keys(report.agent_metrics).length} agents`],
    ['MAX VOLATILITY', number(maximumVolatility, 4), `${report.warning_timeline.length} warnings`],
  ];

  const validationRows = Object.entries(report.validation_metrics);
  const coverageRows = [
    ['Price observations', path.length],
    ['Recorded events', report.events.length],
    ['Recent order records', report.recent_orders.length],
    ['Matched trades', report.order_flow.trades.length],
    ['Simulated agents', Object.keys(report.agent_metrics).length],
    ['Warning transitions', report.warning_timeline.length],
  ];

  const definitions = [
    ['Spread', 'The ask price minus the bid price. A wider spread indicates more simulated trading friction.'],
    ['Depth', 'The quantity resting in the simulated order book. Minimum depth shows the thinnest observed point in this run.'],
    ['Imbalance', 'The relative difference between displayed buy and sell quantity. It describes pressure, not a price prediction.'],
    ['Market impact', 'The absolute price movement associated with consecutive simulated market states, expressed in basis points.'],
    ['Slippage', 'The difference between an expected execution reference and the simulated fill price.'],
    ['Match rate', 'Matched orders as a percentage of submitted orders. It describes this simulated book and configuration only.'],
    ['P&L', 'Profit and loss from simulated positions. Realized P&L uses closed trades; unrealized P&L marks open positions to the final simulated price.'],
    ['Warning', 'A detector transition caused by a configured threshold. It is not investment advice or a verified real-market forecast.'],
  ];
  const candleValues = reportCandles.flatMap((candle) => [candle.high, candle.low]);
  const candleLow = Math.min(...candleValues);
  const candleHigh = Math.max(...candleValues);
  const candlePadding = Math.max((candleHigh - candleLow) * 0.12, 0.005);
  const candleFloor = candleLow - candlePadding;
  const candleCeiling = candleHigh + candlePadding;
  const candleY = (price: number) => 260 - ((price - candleFloor) / (candleCeiling - candleFloor)) * 230;
  const candleStep = 800 / Math.max(reportCandles.length, 16);

  return (
    <main className="report-page min-h-screen bg-black px-4 py-5 text-white sm:px-7 lg:px-10">
      <header className="report-actions mx-auto flex max-w-[1320px] flex-wrap items-center justify-between gap-3 border-b border-gray-800 pb-4">
        <a href="/dashboard" className="inline-flex items-center gap-2 text-[10px] tracking-[0.13em] text-gray-500 transition-colors hover:text-white">
          <ArrowLeft size={14} /> RETURN TO DASHBOARD
        </a>
        <div className="flex max-w-full flex-wrap items-center gap-2">
          <ThemeToggle />
          <button type="button" onClick={() => downloadReport(report)} className="command-button">
            <Download size={13} /> Download JSON
          </button>
          <button type="button" onClick={downloadPdf} disabled={pdfDownloading} className="command-button command-button--export">
            <Download size={13} /> {pdfDownloading ? 'Preparing PDF' : 'Download PDF'}
          </button>
          <button type="button" onClick={() => window.print()} className="command-button">
            <Printer size={13} /> PRINT VIEW
          </button>
        </div>
      </header>

      <article className="mx-auto w-full min-w-0 max-w-[1320px] overflow-hidden">
        <section className="grid min-w-0 gap-6 border-b border-gray-800 py-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div className="min-w-0">
            <div className="text-[10px] tracking-[0.2em] text-[#f0b35a]">SENTINEL / NASDAQ MARKET MICROSTRUCTURE</div>
            <h1 className="mt-3 whitespace-normal break-words text-3xl font-semibold tracking-normal sm:text-4xl">Simulation session record</h1>
            <p className="mt-3 max-w-2xl whitespace-normal break-words text-sm leading-6 text-gray-400">
              Observed market quality, execution activity, and agent outcomes from one completed synthetic session.
            </p>
          </div>
          <dl className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-6 gap-y-2 text-[10px] leading-5 sm:grid-cols-3 lg:text-right">
            <div className="min-w-0"><dt className="text-gray-600">SCENARIO</dt><dd className="break-words text-gray-300">{humanize(report.run_config.scenario)}</dd></div>
            <div className="min-w-0"><dt className="text-gray-600">PRESET</dt><dd className="break-words text-gray-300">{humanize(report.run_config.preset)}</dd></div>
            <div className="min-w-0"><dt className="text-gray-600">SEED</dt><dd className="break-words text-gray-300">{report.run_config.seed ?? 'UNSEEDED'}</dd></div>
            <div className="min-w-0"><dt className="text-gray-600">ELAPSED</dt><dd className="break-words text-gray-300">{number(report.run_config.elapsed_seconds, 1)} SIM SEC</dd></div>
            <div className="min-w-0"><dt className="text-gray-600">LATENCY</dt><dd className="break-words text-gray-300">{humanize(report.run_config.latency_mode)}</dd></div>
            <div className="min-w-0"><dt className="text-gray-600">GENERATED</dt><dd className="break-words text-gray-300">{new Date(report.generated_at).toLocaleString()}</dd></div>
          </dl>
        </section>

        <h2 className="report-section-title">Executive summary</h2>
        <section className="report-headline grid border-b border-l border-gray-800 sm:grid-cols-2 lg:grid-cols-6">
          {headline.map(([label, value, note], index) => (
            <div key={label} className="min-w-0 border-r border-gray-800 p-4">
              <div className="text-[9px] tracking-[0.15em] text-gray-600">{String(index + 1).padStart(2, '0')} / {label}</div>
              <div className="mt-3 truncate text-xl font-medium text-gray-100">{value}</div>
              <div className="mt-1 truncate text-[10px] text-gray-500">{note}</div>
            </div>
          ))}
        </section>

        <section className="mt-7 grid gap-7 xl:grid-cols-[1.55fr_0.65fr]">
          <div className="border border-gray-800">
            <div className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
              <h2 className="text-[10px] tracking-[0.16em] text-gray-300">REPORT CANDLE TAPE</h2>
              <span className="text-[9px] text-gray-600">5-SECOND OHLC / SPREAD + DEPTH BELOW</span>
            </div>
            <div className="h-[360px] p-3">
              {reportCandles.length ? <svg className="h-full w-full" viewBox="0 0 900 300" role="img" aria-label="Five-second OHLC candle chart for this simulation report">
                {[0, 1, 2, 3, 4].map((index) => {
                  const price = candleFloor + (candleCeiling - candleFloor) * index / 4;
                  return <g key={index}><line x1="8" x2="820" y1={candleY(price)} y2={candleY(price)} className="report-chart-grid" /><text x="834" y={candleY(price) + 3} className="report-chart-label">{price.toFixed(3)}</text></g>;
                })}
                {reportCandles.map((candle, index) => {
                  const x = 16 + index * candleStep;
                  const rising = candle.close >= candle.open;
                  const bodyTop = candleY(Math.max(candle.open, candle.close));
                  const bodyBottom = candleY(Math.min(candle.open, candle.close));
                  return <g key={candle.time} className={`report-candle ${rising ? 'up' : 'down'}`}>
                    <title>{`${candle.time / 1000}s · O ${candle.open.toFixed(3)} H ${candle.high.toFixed(3)} L ${candle.low.toFixed(3)} C ${candle.close.toFixed(3)}`}</title>
                    <line className="report-candle-wick upper" x1={x} x2={x} y1={candleY(candle.high)} y2={bodyTop} />
                    <rect x={x - Math.max(2, candleStep * 0.3)} y={bodyTop} width={Math.max(4, candleStep * 0.6)} height={Math.max(2, bodyBottom - bodyTop)} />
                    <line className="report-candle-wick lower" x1={x} x2={x} y1={bodyBottom} y2={candleY(candle.low)} />
                  </g>;
                })}
                <text x="16" y="291" className="report-chart-label">{reportCandles[0].time / 1000}s</text>
                <text x="820" y="291" textAnchor="end" className="report-chart-label">{reportCandles.at(-1)!.time / 1000}s</text>
              </svg> : <div className="grid h-full place-items-center text-xs text-gray-600">No price observations recorded.</div>}
            </div>
            <div className="h-28 border-t border-gray-800 p-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <XAxis dataKey="timestamp" hide />
                  <YAxis yAxisId="depth" tick={{ fill: '#666', fontSize: 9 }} width={58} />
                  <YAxis yAxisId="spread" orientation="right" tick={{ fill: '#666', fontSize: 9 }} width={48} />
                  <Tooltip contentStyle={{ background: '#080808', border: '1px solid #333', fontSize: 11 }} />
                  <Line yAxisId="depth" name="Depth" type="stepAfter" dataKey="depth" stroke="#6fa8dc" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  <Line yAxisId="spread" name="Spread" type="stepAfter" dataKey="spread" stroke="#b28a3e" strokeWidth={1} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="border border-gray-800 p-5">
            <div className="text-[10px] tracking-[0.16em] text-[#f0b35a]">RUN FINDINGS</div>
            <ol className="mt-5 space-y-6 text-sm leading-6 text-gray-300">
              {findings.map((finding, index) => (
                <li key={finding} className="grid grid-cols-[2rem_1fr] gap-2">
                  <span className="text-gray-600">{String(index + 1).padStart(2, '0')}</span>
                  <span>{finding}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="mt-7 grid gap-7 xl:grid-cols-[1fr_0.65fr]">
          <div className="overflow-x-auto border border-gray-800">
            <div className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
              <h2 className="text-[10px] tracking-[0.16em] text-gray-300">Participant outcomes</h2>
              <span className="text-[9px] text-gray-600">GROUPED BY RULE SET</span>
            </div>
            <table className="w-full min-w-[680px] text-xs">
              <thead className="border-b border-gray-800 text-[9px] tracking-[0.13em] text-gray-600">
                <tr><th className="px-4 py-3 text-left">AGENT TYPE</th><th className="px-4 py-3 text-right">COUNT</th><th className="px-4 py-3 text-right">TRADES</th><th className="px-4 py-3 text-right">NET POSITION</th><th className="px-4 py-3 text-right">HALTED</th><th className="px-4 py-3 text-right">TOTAL PNL</th></tr>
              </thead>
              <tbody>
                {Object.entries(agents).sort(([, a], [, b]) => b.trades - a.trades).map(([name, row]) => (
                  <tr key={name} className="border-b border-gray-900 last:border-b-0">
                    <td className="px-4 py-3 text-gray-300">{humanize(name)}</td>
                    <td className="px-4 py-3 text-right text-gray-500">{row.count}</td>
                    <td className="px-4 py-3 text-right">{row.trades}</td>
                    <td className="px-4 py-3 text-right">{signed(row.position, 0)}</td>
                    <td className="px-4 py-3 text-right">{row.halted}</td>
                    <td className={`px-4 py-3 text-right ${row.pnl >= 0 ? 'text-[#56d89a]' : 'text-red-400'}`}>{signed(row.pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="border border-gray-800 p-5">
            <div className="text-[10px] tracking-[0.16em] text-gray-300">Execution accounting</div>
            <dl className="mt-4 divide-y divide-gray-900 text-xs">
              {[
                ['ORDER SUBMISSIONS', report.order_flow.submitted_orders],
                ['TRADE MATCHES', report.order_flow.trades.length],
                ['CANCEL REQUESTS', report.order_flow.cancel_requests],
                ['ACCEPTED CANCELS', report.order_flow.accepted_cancels],
                ['TERMINAL CANCELS', report.order_flow.terminal_cancels],
                ['BUY VOLUME', report.order_flow.summary.buy_volume],
                ['SELL VOLUME', report.order_flow.summary.sell_volume],
                ['MEAN IMPACT', `${number(report.validation_metrics.impact_bps_mean, 4)} bps`],
                ['MEAN SLIPPAGE', `${number(report.validation_metrics.slippage_bps_mean, 4)} bps`],
              ].map(([label, value]) => <div key={label} className="flex items-center justify-between gap-4 py-2.5"><dt className="text-gray-500">{label}</dt><dd className="text-gray-200">{value}</dd></div>)}
            </dl>
          </div>
        </section>

        <section className="report-research mt-7 grid gap-7 xl:grid-cols-[1fr_1fr]">
          <div className="border border-gray-800 p-5">
            <h2 className="text-[10px] tracking-[0.16em] text-gray-300">VALIDATION MEASUREMENTS</h2>
            <p className="mt-3 text-xs leading-5 text-gray-500">All values below are calculated from the recorded simulator state path and execution counters.</p>
            <dl className="mt-4 divide-y divide-gray-900 text-xs">
              {validationRows.map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-5 py-2.5">
                  <dt className="text-gray-500">{reportLabel(label)}</dt>
                  <dd className="text-right text-gray-200">{number(value, 6)}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="border border-gray-800 p-5">
            <h2 className="text-[10px] tracking-[0.16em] text-gray-300">DATA COVERAGE</h2>
            <p className="mt-3 text-xs leading-5 text-gray-500">This identifies how much evidence is behind the summary. A short run should not be treated as a stable estimate.</p>
            <dl className="mt-4 divide-y divide-gray-900 text-xs">
              {coverageRows.map(([label, value]) => (
                <div key={String(label)} className="flex items-center justify-between gap-5 py-2.5">
                  <dt className="text-gray-500">{label}</dt>
                  <dd className="text-right text-gray-200">{Number(value).toLocaleString()}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className="mt-7 grid gap-7 pb-10 lg:grid-cols-3">
          <div className="border border-gray-800 p-5">
            <h2 className="text-[10px] tracking-[0.16em] text-gray-300">Detector record</h2>
            {report.warning_timeline.length ? (
              <div className="mt-4 max-h-64 divide-y divide-gray-900 overflow-y-auto text-[10px]">
                {report.warning_timeline.map((warning, index) => (
                  <div key={`${warning.timestamp}-${index}`} className="grid grid-cols-[3.5rem_1fr_auto] gap-3 py-3">
                    <span className="text-gray-600">{number(Number(warning.timestamp), 1)}s</span>
                    <span className="text-gray-300">{humanize(String(warning.detector ?? 'warning'))}</span>
                    <span className="text-[#f0b35a]">{humanize(String(warning.warning_level ?? warning.pattern ?? 'detected'))}</span>
                  </div>
                ))}
              </div>
            ) : <p className="mt-4 text-xs leading-5 text-gray-600">No detector state crossed a warning threshold during this run.</p>}
          </div>

          <div className="border border-gray-800 p-5">
            <h2 className="text-[10px] tracking-[0.16em] text-gray-300">EVENT LEDGER</h2>
            <dl className="mt-4 divide-y divide-gray-900 text-xs">
              {Object.entries(eventCounts).sort(([, a], [, b]) => b - a).map(([name, count]) => (
                <div key={name} className="flex justify-between py-2.5"><dt className="text-gray-500">{humanize(name)}</dt><dd>{count}</dd></div>
              ))}
            </dl>
          </div>

          <div className="border border-gray-800 p-5 text-xs leading-5 text-gray-500">
            <h2 className="text-[10px] tracking-[0.16em] text-gray-300">Method and limitations</h2>
            <p className="mt-4">Values are calculated from the simulator&apos;s recorded state path and final execution counters. Agent PnL is marked to the final simulated price.</p>
            <p className="mt-4">This is one synthetic run under the listed seed, scenario, population, and latency assumptions. It is not evidence of real-market profitability or a forecast of future prices.</p>
            <div className="mt-5 border-t border-gray-900 pt-4 text-[9px] tracking-[0.12em] text-gray-600">
              {report.run_config.venue} / {report.run_config.steps.toLocaleString()} STEPS / {report.run_config.speed}X PLAYBACK / INFORMED ACCESS {report.run_config.informed_access ? 'ON' : 'OFF'}
            </div>
          </div>
        </section>

        <section className="report-definitions mt-7 border-t border-gray-800 pt-7 pb-10">
          <div className="max-w-3xl">
            <h2 className="text-[10px] tracking-[0.16em] text-gray-300">TERMS USED IN THIS REPORT</h2>
            <p className="mt-3 text-xs leading-5 text-gray-500">Short definitions are included so this report can be read without prior market-microstructure knowledge.</p>
          </div>
          <dl className="mt-5 grid gap-x-8 gap-y-4 md:grid-cols-2">
            {definitions.map(([term, definition]) => (
              <div key={term} className="border-b border-gray-900 pb-4">
                <dt className="text-sm font-medium text-gray-200">{term}</dt>
                <dd className="mt-1 text-xs leading-5 text-gray-500">{definition}</dd>
              </div>
            ))}
          </dl>
        </section>
      </article>
    </main>
  );
}
