import Link from 'next/link';

const CHAPTERS = [
  ['quick', 'Quick start'],
  ['sim', 'The simulator'],
  ['read', 'Reading the market'],
  ['signals', 'Signals'],
  ['scen', 'Scenarios'],
  ['reports', 'Session reports'],
  ['api', 'API'],
  ['limits', 'Safety and limitations'],
] as const;

const AGENTS: Array<[string, string, number]> = [
  ['MarketMaker', 'Quotes a four-level ladder each side around the microprice; skews for inventory, widens on one-sided flow.', 3],
  ['HFT', 'Lowest-latency tier. Quotes only the side the queue imbalance favours, never crosses to enter, stays near flat.', 2],
  ['Institutional', 'Works a large parent order against a TWAP schedule: passive when on track, aggressive when behind.', 2],
  ['Retail', 'Moving-average crossovers with a resting stop-loss; small, infrequent orders.', 10],
  ['Informed', 'Gets an occasional noisy read of the fundamental and trades it when the edge beats costs (oracle on).', 3],
  ['Noise', 'Random flow that gets busier after big moves; passive orders mostly at the touch.', 10],
  ['LiquidityTrader', 'Must complete an exogenous quantity, sliced into child orders.', 1],
  ['Momentum', 'Channel breakouts, confirmed by aggressor flow, with a trailing stop.', 2],
  ['MeanReversion', 'Bollinger + RSI fades with a band-width stop.', 2],
  ['Sentiment', 'Herds or fades the recent trend; each position is held for minutes, not hours.', 5],
  ['Spoofing', 'Layers quotes it does not intend to fill. Enabled only in spoofing_stress.', 0],
];

const TERMS = [
  ['Candles (OHLC)', 'Each candle summarizes mid-price samples over an interval: open, high, low, close. Light closed at or above the open; orange closed below.'],
  ['L2 order book', 'Resting buy (bid) and sell (ask) quantity at each price level, best prices nearest the mid.'],
  ['Mid price', '(best bid + best ask) / 2.'],
  ['Spread', 'Best ask − best bid, shown in ticks and in basis points of the mid (1 bp = 0.01%).'],
  ['Depth', 'Total resting quantity on one side across visible levels.'],
  ['Imbalance', '(bid depth − ask depth) / (bid depth + ask depth); negative is sell-heavy.'],
  ['VWAP', 'Volume-weighted average traded price. The dashboard estimates it from the live flow; the report computes it from recorded trades.'],
  ['Aggressor flow', 'Volume from orders that crossed the spread, split by buy and sell, over the last 10 seconds.'],
];

const SCENARIOS = [
  ['normal', '1.0×', '1.0×', '1.0×', 'Balanced session with non-adversarial agents.'],
  ['market_open', '2.5×', '1.4×', '1.35×', 'Pre-open accumulation, uniform-price uncross, wide fast open.'],
  ['liquidity_shock', '1.0×', '1.0×', '1.0×', 'Quote withdrawal, aggressive flow, measured recovery.'],
  ['institutional_execution', '1.25×', '1.2×', '1.15×', 'Elevated institutional parent-order activity.'],
  ['volatility_spike', '3.0×', '2.8×', '0.75×', 'Noisy regime, wider quoting, smaller child orders.'],
  ['spoofing_stress', '1.75×', '1.5×', '0.9×', 'Quote-layering agents enabled.'],
  ['close_auction', '1.6×', '1.0×', '1.8×', 'Deeper displayed book near a synthetic close.'],
];

const API = [
  ['GET', '/api/health', 'Service status.'],
  ['GET', '/api/sandbox/presets', 'Agent presets and compositions.'],
  ['GET', '/api/sandbox/scenarios', 'Scenario definitions and multipliers.'],
  ['POST', '/api/sandbox/create', 'Start a run (preset, scenario, seed, latency, oracle, speed).'],
  ['PUT', '/api/sandbox/speed', 'Change playback speed of the running session.'],
  ['POST', '/api/simulation/stop', 'Stop the run and freeze the report.'],
  ['GET', '/api/simulation/export', 'Download the session record.'],
  ['GET', '/api/simulation/report', 'The frozen session report (JSON).'],
  ['GET', '/api/simulation/report.pdf', 'The same report as a PDF.'],
  ['WS', '/ws', 'One market_update frame per tick.'],
];

const BANDS = [
  ['safe', '< 0.20', 'bg-paper-3'],
  ['caution', '≥ 0.20', 'bg-caution-paper'],
  ['warning', '≥ 0.40', 'bg-accent'],
  ['critical', '≥ 0.60', 'bg-ink text-fg'],
];

const h2 = 'm-0 font-display text-2xl font-semibold';
const prose = 'm-0 max-w-[720px]';

export default function DocsPage() {
  return (
    <div className="on-paper min-h-screen bg-paper text-[15px] leading-[1.65] text-ink">
      <header className="bg-ink text-fg">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-5">
            <Link href="/" className="inline-flex min-h-10 items-center font-display text-xl font-bold no-underline">SENTINEL</Link>
            <span className="text-fg-muted">Documentation</span>
          </div>
          <div className="flex gap-2">
            <a href="https://github.com/macayu17/sentinel" className="btn">GitHub</a>
            <Link href="/start" className="btn btn-accent">Open simulator</Link>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1200px] flex-wrap items-start gap-10 px-4 pb-[72px] pt-9 sm:px-6">
        <nav aria-label="Chapters" className="flex flex-[1_1_220px] flex-col gap-0.5 text-sm md:sticky md:top-4">
          <span className="px-3 pb-1.5 text-xs text-paper-muted">Contents</span>
          {CHAPTERS.map(([id, title], index) => (
            <a key={id} href={`#${id}`} className="flex min-h-9 items-center gap-2.5 rounded-lg px-3 font-medium no-underline hover:bg-paper-3">
              <span className="w-[18px] text-paper-muted">{index + 1}</span>{title}
            </a>
          ))}
        </nav>

        <main className="flex min-w-0 flex-[999_1_640px] flex-col gap-11">
          <section className="flex flex-col gap-2">
            <h1 className="m-0 font-display text-[40px] font-semibold leading-[1.1] tracking-[-0.02em]">Read the market. Then run it.</h1>
            <p className="m-0 max-w-[680px] text-[17px] text-paper-fg2">A practical guide to SENTINEL&apos;s simulator, its market measurements and its session reports, written for a first run.</p>
          </section>

          <section id="quick" className="flex flex-col gap-3">
            <h2 className={h2}>1. Quick start</h2>
            <ol className="m-0 flex max-w-[720px] list-decimal flex-col gap-1.5 pl-5">
              <li><strong>Choose a preset.</strong> Balanced (40 agents) mixes every non-adversarial agent type and is the best first run.</li>
              <li><strong>Choose a scenario.</strong> Normal Session is the baseline; the others deliberately change liquidity or behaviour.</li>
              <li><strong>Launch and observe.</strong> Candles, the L2 book, signals, agents and execution records update together over the WebSocket.</li>
              <li><strong>Stop and review.</strong> Stopping freezes a session report you can inspect or download as JSON or PDF.</li>
            </ol>
            <pre className="m-0 overflow-x-auto rounded-xl bg-ink px-4 py-3.5 font-mono text-[13px] text-fg">{`docker-compose up --build
# dashboard  http://localhost:3000/dashboard
# api        http://localhost:8000  ·  ws://localhost:8000/ws`}</pre>
          </section>

          <section id="sim" className="flex flex-col gap-3">
            <h2 className={h2}>2. The simulator</h2>
            <p className={prose}>A synthetic continuous double auction. Rule-based agents submit limit, market, post-only, IOC and stop orders to a matching engine with price-time priority; some scenarios add an opening uncross or a closing auction. Each agent sits in a latency tier, from 1 μs (co-located HFT) to milliseconds (retail). A hidden fundamental value moves with occasional news jumps; informed agents see it early, the market at large only after a delay. A fixed seed reproduces a run exactly.</p>
            <div className="overflow-x-auto rounded-xl bg-paper-2">
              <table className="w-full min-w-[600px] border-collapse text-sm">
                <thead><tr className="text-left text-xs text-paper-muted"><th scope="col" className="px-3.5 py-2.5 font-medium">Agent type</th><th scope="col" className="p-2.5 font-medium">Behaviour</th><th scope="col" className="px-3.5 py-2.5 text-right font-medium">Balanced</th></tr></thead>
                <tbody>
                  {AGENTS.map(([name, about, count]) => (
                    <tr key={name} className="border-t border-paper-rule"><td className="px-3.5 py-2 font-semibold">{name}</td><td className="px-2.5 py-2 text-paper-fg2">{about}</td><td className="px-3.5 py-2 text-right">{count}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section id="read" className="flex flex-col gap-3">
            <h2 className={h2}>3. Reading the market</h2>
            <dl className="m-0 grid gap-2.5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))' }}>
              {TERMS.map(([term, meaning]) => (
                <div key={term} className="rounded-xl bg-paper-2 px-4 py-3.5"><dt className="font-bold">{term}</dt><dd className="m-0 mt-1 text-sm text-paper-fg2">{meaning}</dd></div>
              ))}
            </dl>
            <p className="m-0 max-w-[720px] text-sm text-paper-muted">Large visible depth can disappear through fills or cancellations, so it is not a guarantee of support.</p>
          </section>

          <section id="signals" className="flex flex-col gap-3">
            <h2 className={h2}>4. Signals</h2>
            <h3 className="m-0 text-base font-bold">Liquidity stress</h3>
            <p className={prose}>A 0 to 1 score; health is 1 − stress. When the trained model file is present it is used (method <code>lobster_nasdaq_model</code>): a calibrated probability that, within the next 60 seconds, the spread reaches 2.5× its recent baseline or visible depth falls to 40% of it. Without the file the backend falls back to <code>adaptive_stress</code>, a diagnostic of the current book against its own trailing baseline, which reports <code>calibrating</code> for its first readings.</p>
            <div className="grid max-w-[720px] grid-cols-2 gap-1.5 sm:grid-cols-4">
              {BANDS.map(([level, range, tone]) => (
                <div key={level} className={`rounded-[10px] px-3 py-2.5 ${tone}`}><strong>{level}</strong><br /><span className="text-[13px] opacity-80">{range}</span></div>
              ))}
            </div>
            <h3 className="m-0 mt-2 text-base font-bold">The model</h3>
            <p className={prose}>A small LightGBM model (7 leaves, 2,000 boosting rounds, settings chosen by random search) on 32 scale-free features, sampled once a second: spread and depth against their 1, 5 and 15 minute baselines, depth and spread changes, book and queue imbalance, the shape of all 10 book levels, realized volatility, aggressor flow, and how recently and how often the book was under stress. The live predictor computes them with the same code used in training. It was trained on five full NASDAQ days from LOBSTER (AAPL, AMZN, GOOG, INTC, MSFT, 2012-06-21) plus 28 simulator sessions weighted to a quarter of the data, then isotonic-calibrated.</p>
            <p className={prose}>Each score below comes from a model that never saw that stock: ROC-AUC 0.90 and average precision 0.62 on average, against 0.70 and 0.36 for a no-learning rule that only reads the current spread and depth. On simulator sessions held out of training it scores ROC-AUC 0.81. Part of the gain comes from the longer baselines: when the last minute was unusually calm, a return to normal spreads counts as a shock, and the model learns to expect it. Logistic regression, random forests, XGBoost, larger LightGBM models and ensembles were compared and scored lower.</p>
            <h3 className="m-0 mt-2 text-base font-bold">Large order detection</h3>
            <p className={prose}>Pattern <code>large_level</code> on the visible order book. Each flag reports <code>side</code>, <code>price</code>, <code>estimated_size</code>, <code>size_multiple</code> (vs the median level), <code>depth_share</code> (of that side) and <code>confidence</code>.</p>
            <p className="m-0 max-w-[720px] rounded-xl bg-ink px-4 py-3.5 text-fg">Read signals as evidence, not predictions. A good question: which change in orders, depth or scenario made this signal move?</p>
          </section>

          <section id="scen" className="flex flex-col gap-3">
            <h2 className={h2}>5. Scenarios</h2>
            <div className="overflow-x-auto rounded-xl bg-paper-2">
              <table className="w-full min-w-[640px] border-collapse text-sm">
                <thead><tr className="text-left text-xs text-paper-muted"><th scope="col" className="px-3.5 py-2.5 font-medium">Scenario</th><th scope="col" className="p-2.5 text-right font-medium">Spread</th><th scope="col" className="p-2.5 text-right font-medium">Vol.</th><th scope="col" className="p-2.5 text-right font-medium">Depth</th><th scope="col" className="px-3.5 py-2.5 font-medium">Description</th></tr></thead>
                <tbody>
                  {SCENARIOS.map(([key, spread, vol, depth, about]) => (
                    <tr key={key} className="border-t border-paper-rule"><td className="px-3.5 py-2"><code>{key}</code></td><td className="px-2.5 py-2 text-right">{spread}</td><td className="px-2.5 py-2 text-right">{vol}</td><td className="px-2.5 py-2 text-right">{depth}</td><td className="px-3.5 py-2 text-paper-fg2">{about}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section id="reports" className="flex flex-col gap-2.5">
            <h2 className={h2}>6. Session reports</h2>
            <p className={prose}>Stopping a run, or letting it reach the close, preserves its final state. The report includes configuration, an executive summary, a candle tape with spread and depth, the detector record, execution accounting, participant outcomes, data coverage, method and limitations, and a glossary. Use JSON for analysis and PDF for a readable record.</p>
            <Link href="/dashboard/session-report" className="btn self-start bg-ink text-fg">Open the latest report</Link>
          </section>

          <section id="api" className="flex flex-col gap-2.5">
            <h2 className={h2}>7. API</h2>
            <div className="overflow-hidden rounded-xl bg-paper-2">
              {API.map(([method, path, about]) => (
                <div key={path} className="grid grid-cols-[52px_1fr] gap-x-3 gap-y-1 border-t border-paper-rule px-3.5 py-2.5 text-sm first:border-t-0 sm:grid-cols-[60px_240px_1fr]">
                  <span className="font-bold text-accent-deep">{method}</span>
                  <code className="justify-self-start">{path}</code>
                  <span className="col-span-2 text-paper-fg2 sm:col-span-1">{about}</span>
                </div>
              ))}
            </div>
          </section>

          <section id="limits" className="flex flex-col gap-2.5 rounded-panel bg-ink px-6 py-[22px] text-fg">
            <h2 className={h2}>8. Safety and limitations</h2>
            <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-fg-2">
              <li>Simulation values and PnL are synthetic.</li>
              <li>Warnings are research signals, not investment advice.</li>
              <li>Results depend on scenario, seed, population, latency and run length.</li>
              <li>Repeat runs before drawing conclusions.</li>
            </ul>
          </section>
        </main>
      </div>
    </div>
  );
}
