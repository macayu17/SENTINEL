'use client';

import { useState } from 'react';
import { mood } from './LiveCard';

const CALM = { bids: [900, 1200, 1500, 1100, 1300, 1000], asks: [800, 1100, 1400, 1250, 1000, 1200] };
const WIDEST = 1600;

/** A six-level toy book. Pull buyers or dump shares and watch a stress-style score react. */
export default function BreakIt() {
  const [bids, setBids] = useState(CALM.bids);
  const [message, setMessage] = useState('calm market. plenty of buyers and sellers.');
  const bidTotal = bids.reduce((a, b) => a + b, 0);
  const askTotal = CALM.asks.reduce((a, b) => a + b, 0);
  // Thin bids and a lopsided book push the score up, the same inputs the real detector weighs.
  const risk = Math.round(Math.min(96, Math.max(8, 100 - (bidTotal / 7000) * 70 + Math.max(0, askTotal - bidTotal) / 300)));
  const [, label, bg, fg] = mood(risk);

  const pull = () => {
    setBids((b) => b.map((size, i) => Math.round(size * (i < 3 ? 0.35 : 0.6))));
    setMessage('market makers pulled their buy orders. the left side is thinning out.');
  };
  const dump = () => {
    setBids((b) => {
      let left = 3000;
      return b.map((size) => { const take = Math.min(size, left); left -= take; return size - take; });
    });
    setMessage('someone sold 3,000 shares at once and ate through the best buy orders.');
  };
  const reset = () => { setBids(CALM.bids); setMessage('calm market. plenty of buyers and sellers.'); };

  return (
    <div className="grid items-stretch gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))' }}>
      <div className="flex flex-col gap-1.5 rounded-card bg-ink p-7 text-fg" role="img" aria-label={`Toy order book: ${bidTotal.toLocaleString('en-US')} shares bid, ${askTotal.toLocaleString('en-US')} offered`}>
        <div className="grid grid-cols-[1fr_72px_1fr] pb-2 text-sm text-[#b9b7b0]"><span>buyers waiting</span><span className="text-center">price</span><span className="text-right">sellers waiting</span></div>
        {bids.map((size, i) => (
          <div key={i} className="grid h-[30px] grid-cols-[1fr_72px_1fr] items-center">
            <div className="flex justify-end"><div className="h-[22px] rounded-l-full rounded-r bg-fg transition-[width] duration-500" style={{ width: `${(size / WIDEST) * 100}%` }} /></div>
            <span className="text-center text-[15px] font-medium">{(99.99 - i * 0.01).toFixed(2)}</span>
            <div className="flex"><div className="h-[22px] rounded-l rounded-r-full bg-accent" style={{ width: `${(CALM.asks[i] / WIDEST) * 100}%` }} /></div>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-[22px] rounded-card bg-paper-3 p-7 text-ink">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col">
            <span className="font-bold">risk score</span>
            <span className="font-display text-[clamp(80px,14vw,120px)] font-extrabold leading-[0.85] tracking-[-0.06em]" style={{ color: risk >= 55 ? 'var(--accent-deep)' : 'var(--ink)' }}>{risk}</span>
          </div>
          <span className="rounded-full px-[18px] py-1.5 font-display text-[28px] font-extrabold" style={{ background: bg === 'var(--paper-3)' ? 'var(--paper)' : bg, color: fg }}>{label}</span>
        </div>
        <p role="status" className="m-0 min-h-[58px] font-display text-2xl font-bold leading-tight tracking-[-0.01em]">{message}</p>
        <div className="mt-auto flex flex-wrap gap-2.5">
          <button type="button" onClick={pull} className="btn btn-pill min-h-[52px] bg-ink px-[22px] text-[17px] font-bold text-fg">pull the buyers</button>
          <button type="button" onClick={dump} className="btn btn-pill btn-accent min-h-[52px] px-[22px] text-[17px] font-bold">dump 3,000 shares</button>
          <button type="button" onClick={reset} className="btn btn-pill min-h-[52px] bg-paper px-[22px] text-[17px] font-bold text-ink">reset</button>
        </div>
      </div>
    </div>
  );
}
