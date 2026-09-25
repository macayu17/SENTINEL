import Link from 'next/link';
import InfoTip from '@/components/InfoTip';
import ThemeToggle from '@/components/ThemeToggle';
import RippleField from '@/components/RippleField';
import WorkspaceDock from '@/components/WorkspaceDock';

const glossary = [
  ['Bid/ask', 'The highest visible buying price and lowest visible selling price.'],
  ['Spread', 'The ask minus the bid. Wider spreads indicate more simulated trading friction.'],
  ['Depth', 'The amount of visible quantity available in the order book.'],
  ['Imbalance', 'The relative difference between bid and ask depth. It is descriptive, not predictive.'],
  ['Volatility', 'The recent magnitude of simulated price movement.'],
  ['P&L', 'Simulated profit and loss. It is not a statement of real-world performance.'],
  ['Basis point', 'One hundredth of one percent. 100 basis points equals 1%.'],
  ['Fill', 'An order, or part of an order, matched against another order.'],
];

export default function DocumentationPage() {
  return <div className="research-shell docs-shell">
    <header className="site-nav">
      <Link href="/" className="brand"><i className="brand-mark" aria-hidden="true" />sentinel</Link>
      <nav aria-label="Documentation navigation"><Link href="/dashboard">Dashboard</Link></nav>
      <ThemeToggle />
    </header>

    <main className="docs-layout">
      <WorkspaceDock mode="docs" />
      <article className="docs-article">
        <header className="docs-hero">
          <RippleField className="docs-ripple" />
          <div className="docs-hero-copy">
            <span className="eyebrow">Field guide / 08 chapters</span>
            <h1>Read the market.<br />Then run it.</h1>
            <p>A practical guide to Sentinel&apos;s simulator, market measurements, and session reports—written for a first run.</p>
            <Link className="primary-button" href="/dashboard#experiment">Open the simulator</Link>
          </div>
          <div className="docs-orientation" aria-label="Guide orientation">
            <span><b>01</b> Configure</span><span><b>02</b> Observe</span><span><b>03</b> Explain</span><span><b>04</b> Review</span>
          </div>
        </header>

        <section id="quick-start">
          <h2>Start your first simulation</h2>
          <ol className="docs-steps">
            <li><strong>Choose a preset.</strong><span>Balanced is a useful first run because it mixes several participant behaviours.</span></li>
            <li><strong>Choose a scenario.</strong><span>Normal Session provides a baseline. Stress scenarios deliberately change liquidity or behaviour.</span></li>
            <li><strong>Launch and observe.</strong><span>Watch candles, the order book, signals, agents, and execution records update together.</span></li>
            <li><strong>Stop and review.</strong><span>Stopping freezes an immutable session report that you can inspect or download.</span></li>
          </ol>
        </section>

        <section id="modes">
          <h2>Simulation and what&apos;s next</h2>
          <div className="docs-mode-grid">
            <div><h3>Simulation</h3><p>A synthetic market where rule-based agents submit orders to Sentinel&apos;s matching engine. Use it to inspect cause and effect under reproducible conditions.</p></div>
            <div><h3>AURORA <span className="eyebrow">Coming soon</span></h3><p>AURORA is not available in this release. Its documentation will be added when the feature is ready.</p></div>
          </div>
        </section>

        <section id="market">
          <h2>Candles and the order book</h2>
          <p>Each candle summarizes received mid-price samples. Green means the close finished at or above the open; red means it finished below. The thin upper and lower wicks show the sampled high and low.</p>
          <p>The depth view shows resting buy and sell quantity by price. Hover or focus a level to inspect it. Large visible depth can disappear through fills or cancellations, so it is not a guarantee of support.</p>
        </section>

        <section id="signals">
          <h2>Read signals as evidence</h2>
          <p>Liquidity health, warning levels, visible concentration, imbalance, and volatility describe the current simulated state. They do not promise what the next price will be.</p>
          <div className="docs-callout"><strong>Good question:</strong> Which change in orders, depth, or scenario caused this signal to move?</div>
        </section>

        <section id="reports">
          <h2>Session reports</h2>
          <p>Stop a simulation to preserve its final state. The report includes configuration, market outcome, price and depth paths, execution accounting, participant outcomes, detector transitions, data coverage, methodology, and limitations.</p>
          <p>Use JSON for further analysis and PDF for a readable research record. A single run is evidence about one seed and configuration, not proof of a general result.</p>
        </section>

        <section id="warnings">
          <h2>Provider warnings <InfoTip term="Provider warning" /></h2>
          <p>A provider warning means one market-data request failed, used an invalid instrument, or returned incomplete data. It does not automatically mean the whole monitor stopped. Check the warning text, covered-symbol count, current phase, and process state together.</p>
        </section>

        <section id="limits">
          <h2>Safety and limitations</h2>
          <ul className="docs-points">
            <li>Simulation values and P&L are synthetic.</li>
            <li>AURORA is not available in this release.</li>
            <li>Warnings are research signals, not investment advice.</li>
            <li>Results depend on scenario, seed, population, latency, and run length.</li>
            <li>Repeat runs before drawing conclusions.</li>
          </ul>
        </section>

        <section id="glossary">
          <h2>Glossary</h2>
          <dl className="docs-glossary">{glossary.map(([term, meaning]) => <div key={term}><dt>{term}</dt><dd>{meaning}</dd></div>)}</dl>
        </section>
      </article>
    </main>
    <footer className="site-footer"><span>Sentinel documentation</span><Link href="/dashboard">Return to dashboard</Link></footer>
  </div>;
}
