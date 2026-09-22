'use client';

import { useEffect, useState } from 'react';
import { useMarketStore } from '@/store/market-store';
import type { OrderLevel } from '@/types/market';

type Selection = { side: 'Bid' | 'Ask'; level: OrderLevel };

export default function DepthInspector() {
  const data = useMarketStore(s => s.marketData);
  const running = useMarketStore(s => s.simulationRunning && s.connected);
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    if (!running) return;
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    const timer = window.setInterval(() => {
      if (!media.matches && !document.hidden) setPhase(value => (value + 1) % 16);
    }, 220);
    return () => clearInterval(timer);
  }, [running]);
  const [hover, setHover] = useState<Selection | null>(null);
  const [held, setHeld] = useState<Selection | null>(null);
  const [capturedBook, setCapturedBook] = useState<typeof data>(null);
  const book = (held ? capturedBook : data)?.order_book;
  const bids = book?.bids.slice(0, 10) ?? [], asks = book?.asks.slice(0, 10) ?? [];
  const peak = Math.max(1, ...bids.concat(asks).map(l => l.size));
  const active = held ?? hover;
  const symbol = data?.market === 'NASDAQ' ? '$' : '₹';
  const select = (side: Selection['side'], level: OrderLevel) => {
    if (held?.side === side && held.level.price === level.price) { setHeld(null); setCapturedBook(null); }
    else { setHeld({ side, level: { ...level } }); setCapturedBook(data); }
  };
  return <section className="depth-inspector" aria-label="Interactive order book">
    <div className="section-heading"><h2>Inside the spread</h2><span>{held ? 'Held snapshot' : 'Live visible depth'}</span></div>
    {!bids.length && !asks.length ? <div className="empty-state">Waiting for the order book.</div> : <>
      <div className="depth-columns"><span>Bid · price / units</span><span>Ask · price / units</span></div>
      {Array.from({ length: Math.max(bids.length, asks.length) }, (_, i) => <div className="depth-pair" key={i}>{(['Bid', 'Ask'] as const).map(side => {
        const level = (side === 'Bid' ? bids : asks)[i];
        if (!level) return <span key={side} />;
        const fill = Math.round(level.size / peak * 16);
        const selected = active?.side === side && active.level.price === level.price;
        const glyphs = Array.from({ length: fill }, (_, col) => !held && running && (col + i + phase) % 16 < 2 ? '*' : '#').join('');
        return <button key={side} className={`depth-level ${side.toLowerCase()} ${selected ? 'inspected' : ''}`} onPointerEnter={() => setHover({ side, level })} onPointerLeave={() => setHover(null)} onFocus={() => setHover({ side, level })} onBlur={() => setHover(null)} onClick={() => select(side, level)} aria-pressed={held?.side === side && held.level.price === level.price} aria-label={`${side} ${symbol}${level.price.toFixed(3)}, ${level.size} units. Select to hold snapshot.`}><span>{symbol}{level.price.toFixed(3)}</span><span className="depth-glyphs" aria-hidden="true"><span>{glyphs}</span>{'·'.repeat(16 - fill)}</span><span>{level.size.toLocaleString()}</span></button>;
      })}</div>)}
      <div className="depth-readout" role="status">{active ? `${held ? 'Held' : 'Inspecting'} ${active.side.toLowerCase()} · ${symbol}${active.level.price.toFixed(3)} · ${active.level.size.toLocaleString()} units` : 'Hover or focus a level. Select to hold a snapshot.'}{held && <button className="text-button" onClick={() => { setHeld(null); setCapturedBook(null); setHover(null); }}>Return to live ↗</button>}</div>
    </>}
  </section>;
}
