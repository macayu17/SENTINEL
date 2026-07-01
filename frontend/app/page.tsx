import Link from 'next/link';
import LandingMouseFx from '@/components/LandingMouseFx';
import ThemeToggle from '@/components/ThemeToggle';

const metrics = [
  ['Latency model', 'event driven'],
  ['Market view', 'order flow'],
  ['Signal layer', 'early warning'],
  ['Mode', 'research safe'],
];

const pillars = [
  ['Microstructure replay', 'Price, spread, depth, inventory, and agent behavior in one compact surface.'],
  ['Execution pressure', 'Large orders, imbalance, match rate, and flow shifts stay visible before they become obvious.'],
  ['Operator console', 'Dense controls, explicit state, exportable runs, and repeatable simulation boundaries.'],
];

const rows = [
  ['BID', '100.02', '18,400', 'safe'],
  ['ASK', '100.06', '12,900', 'thin'],
  ['FLOW', '+0.41', 'buy pressure', 'watch'],
  ['DEPTH', '387', 'modeled book', 'stable'],
  ['PNL', '+12.08', 'paper run', 'open'],
  ['EVENT', 'LQ-17', 'large order', 'flagged'],
];

export default function Home() {
  return (
    <main className="landing-shell min-h-screen overflow-hidden">
      <LandingMouseFx />
      <section id="top" className="landing-hero relative border-b">
        <div className="landing-grid" />
        <div className="landing-scan landing-scan--one" />
        <div className="landing-scan landing-scan--two" />
        <div className="landing-chart-backdrop" aria-hidden="true">
          <div className="landing-chart-panel landing-chart-panel--one">
            <span className="landing-candle landing-candle--up" />
            <span className="landing-candle landing-candle--down" />
            <span className="landing-candle landing-candle--up landing-candle--tall" />
            <span className="landing-candle landing-candle--up" />
            <span className="landing-candle landing-candle--down landing-candle--short" />
            <span className="landing-candle landing-candle--up landing-candle--tall" />
            <span className="landing-chart-line" />
          </div>
          <div className="landing-chart-panel landing-chart-panel--two">
            <span className="landing-volume landing-volume--one" />
            <span className="landing-volume landing-volume--two" />
            <span className="landing-volume landing-volume--three" />
            <span className="landing-volume landing-volume--four" />
            <span className="landing-chart-line landing-chart-line--alt" />
          </div>
        </div>

        <header className="landing-nav relative z-10 flex items-center justify-between px-5 py-4 md:px-8">
          <a href="#top" className="flex items-center gap-3">
            <span className="landing-mark" />
            <span className="font-mono text-sm font-bold tracking-[0.32em]">SENTINEL</span>
          </a>
          <nav className="hidden items-center gap-6 font-mono text-[11px] uppercase tracking-[0.18em] md:flex">
            <a href="#system">System</a>
            <a href="#console">Console</a>
            <a href="#scope">Scope</a>
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link href="/dashboard" className="landing-button landing-button--solid">
              Open Console
            </Link>
          </div>
        </header>

        <div className="relative z-10 grid items-center gap-10 px-5 pb-12 pt-7 md:px-8 md:pt-9 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="max-w-4xl">
            <div className="landing-kicker">Smart early-warning network for trading systems</div>
            <h1 className="mt-4 max-w-4xl text-5xl font-semibold leading-[0.94] tracking-[-0.035em] md:text-7xl lg:text-[5.7rem]">
              Market structure before the market narrative.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 md:text-lg">
              Sentinel is a research console for order-book simulation, liquidity stress,
              agent behavior, and execution-risk monitoring.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href="/dashboard" className="landing-button landing-button--solid">
                Launch Dashboard
              </Link>
              <a href="#system" className="landing-button">
                Read System
              </a>
            </div>
          </div>

          <div className="landing-terminal font-mono">
            <div className="flex items-center justify-between border-b px-2 pb-3 text-[10px] uppercase tracking-[0.22em]">
              <span>Kernel Surface</span>
              <span className="landing-live">connected</span>
            </div>
            <div className="grid grid-cols-4 border-b py-3 text-[10px] uppercase tracking-[0.16em] opacity-70">
              <span>type</span>
              <span>price</span>
              <span>size</span>
              <span>state</span>
            </div>
            {rows.map((row, index) => (
              <div
                key={row.join('-')}
                className="landing-terminal-row grid grid-cols-4 border-b py-3 text-sm last:border-0"
                style={{ animationDelay: `${index * 90}ms` }}
              >
                <span className={row[0] === 'ASK' ? 'landing-red' : 'landing-green'}>{row[0]}</span>
                <span>{row[1]}</span>
                <span className="opacity-70">{row[2]}</span>
                <span className="landing-amber">{row[3]}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="system" className="landing-section landing-metrics scroll-mt-24">
        <div className="px-5 pb-2 pt-8 md:px-8">
          <div className="landing-kicker">System / telemetry baseline</div>
        </div>
        <div className="grid md:grid-cols-4">
          {metrics.map(([label, value]) => (
            <div key={label} className="landing-metric">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] opacity-60">{label}</div>
              <div className="mt-3 text-2xl font-semibold">{value}</div>
            </div>
          ))}
        </div>
      </section>

      <section id="console" className="landing-section landing-console scroll-mt-24 px-5 py-16 md:px-8">
        <div className="grid gap-10 lg:grid-cols-[0.82fr_1.18fr]">
          <div>
            <div className="landing-kicker">What it gives you</div>
            <h2 className="mt-4 max-w-xl text-4xl font-semibold leading-tight tracking-[-0.025em] md:text-5xl">
              A console for experiments that need more than a chart.
            </h2>
          </div>
          <div className="grid gap-3">
            {pillars.map(([title, body]) => (
              <article key={title} className="landing-card">
                <h3 className="font-mono text-sm font-bold uppercase tracking-[0.16em]">{title}</h3>
                <p className="mt-3 max-w-2xl leading-7">{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="scope" className="landing-final scroll-mt-24 px-5 py-16 md:px-8">
        <div className="grid gap-6 md:grid-cols-[1fr_auto] md:items-end">
          <div>
            <div className="landing-kicker">Research first</div>
            <h2 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight tracking-[-0.025em]">
              Built to inspect risk, not hide it behind a glossy UI.
            </h2>
          </div>
          <Link href="/dashboard" className="landing-button landing-button--inverse">
            Enter Sentinel
          </Link>
        </div>
      </section>
    </main>
  );
}
