'use client';

import { useState } from 'react';

const SCENARIOS: Array<[string, string, string]> = [
  ['normal', 'normal day', 'a calm, normal trading day. nobody is trying to break anything.'],
  ['market_open', 'market open', 'orders pile up before the bell, then everything starts at once.'],
  ['liquidity_shock', 'liquidity shock', 'buyers and sellers suddenly pull their orders. can sentinel see it coming?'],
  ['institutional_execution', 'big fund selling', 'a big fund chops a huge order into tiny pieces so nobody notices.'],
  ['volatility_spike', 'volatility spike', 'prices swing hard and every bot gets nervous.'],
  ['spoofing_stress', 'spoofing', 'some bots place fake orders just to trick the others.'],
  ['close_auction', 'market close', 'everyone rushes to trade before the closing bell.'],
];

export default function ScenarioPicker() {
  const [current, setCurrent] = useState('liquidity_shock');
  const description = SCENARIOS.find(([key]) => key === current)![2];
  return (
    <>
      <div role="tablist" aria-label="Scenarios" className="flex flex-wrap gap-2.5">
        {SCENARIOS.map(([key, label]) => (
          <button key={key} id={`tab-${key}`} type="button" role="tab" aria-selected={key === current} aria-controls="scenario-panel" onClick={() => setCurrent(key)}
            className={`btn btn-pill min-h-[50px] px-[22px] text-[17px] font-bold text-ink ${key === current ? 'bg-accent' : 'bg-paper-3'}`}>
            {label}
          </button>
        ))}
      </div>
      <p id="scenario-panel" role="tabpanel" aria-labelledby={`tab-${current}`} className="m-0 max-w-[1000px] font-display text-[clamp(30px,5vw,52px)] font-bold leading-[1.05] tracking-[-0.03em]">{description}</p>
    </>
  );
}
