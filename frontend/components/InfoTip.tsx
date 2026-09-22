'use client';

const TERM_HELP: Record<string, string> = {
  'bid/ask': 'The best current buying price and selling price in the simulated order book.',
  spread: 'The gap between the best ask and best bid. A wider spread usually means trading is more expensive.',
  imbalance: 'The relative difference between visible bid and ask quantity. It describes pressure, not a price forecast.',
  depth: 'The total quantity resting in the visible order book.',
  inventory: 'The net position held by the simulated agents.',
  'realized pnl': 'Profit or loss from positions that have already been closed.',
  'unrealized pnl': 'Profit or loss on positions that are still open, marked to the current simulated price.',
  'total pnl': 'Realized and unrealized simulated profit or loss combined.',
  regime: 'The configured market environment, such as a normal session or liquidity shock.',
  session: 'The current phase of the simulated trading day.',
  activity: 'A multiplier controlling how actively simulated participants submit orders.',
  latency: 'The delay between an agent decision and its order reaching the exchange simulator.',
  'latent value': 'The simulator\'s hidden reference value. Only informed agents can see it when informed access is enabled.',
  'reference gap': 'The distance between the visible market price and the hidden reference value, measured in basis points.',
  'aggressor flow': 'Buy volume minus sell volume from orders that immediately sought execution.',
  'liquidity health': 'A 0-100 summary of current spread, depth, imbalance, and volatility conditions.',
  'warning level': 'The current detector state. It is a simulation warning, not investment advice.',
  volatility: 'How much the simulated price has been moving over the recent observation window.',
  preset: 'A predefined population of market makers, institutions, retail traders, and other simulated agents.',
  'start price': 'The initial mid-price used when the synthetic market is created.',
  speed: 'Playback speed for simulation time. It changes pacing, not the configured market scenario.',
  scenario: 'A reproducible set of market conditions used to stress or observe the simulator.',
  'latency model': 'The rule used to delay simulated orders before they reach the matching engine.',
  'informed access': 'Allows selected synthetic agents to observe the hidden reference process.',
};

export default function InfoTip({ term, children }: { term: string; children?: string }) {
  const text = children ?? TERM_HELP[term.toLowerCase()] ?? 'More information about this measurement.';
  return (
    <details className="info-tip">
      <summary aria-label={`About ${term}`}>i</summary>
      <span className="info-tip-box" role="note"><strong>{term}</strong>{text}</span>
    </details>
  );
}
