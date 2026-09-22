import Link from 'next/link';
import ThemeToggle from '@/components/ThemeToggle';
import CharacterField from '@/components/CharacterField';

export default function Home() {
  return <div className="research-shell">
    <header className="site-nav"><Link href="/" className="brand"><i className="brand-mark" aria-hidden="true" />sentinel</Link><nav aria-label="Main navigation"><a href="#research">The research</a><Link href="/dashboard">Workspace ↗</Link></nav><ThemeToggle /></header>
    <main>
      <section className="home-hero"><div><div className="eyebrow">A laboratory for market microstructure</div><h1>There’s a market<br />beneath the price.</h1><p>Watch agents trade. See liquidity shift. Study what happens before a quiet order book becomes an unstable one.</p><Link className="primary-button" href="/dashboard">Explore the workspace ↗</Link><span className="hero-caption">Multi-agent simulation · research environment</span></div><CharacterField /></section>
      <section className="home-details" id="research">{[
        ['01 / Set the conditions', 'Build a market.', 'Choose an agent population, a latency model, and a scenario worth investigating.'],
        ['02 / Observe the response', 'Read between trades.', 'Follow the price, the book, and the agents behind each change.'],
        ['03 / Examine the evidence', 'Keep the experiment.', 'Export a run to inspect events, compare behavior, and explain what happened.'],
      ].map(([label, title, body]) => <article key={title}><span className="eyebrow">{label}</span><h2>{title}</h2><p>{body}</p></article>)}</section>
    </main><footer className="site-footer"><span>Sentinel / market microstructure research</span><span>Simulated markets. No order execution.</span></footer>
  </div>;
}
