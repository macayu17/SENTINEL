'use client';

import { useEffect, useState } from 'react';

interface Bar { o: number; c: number; h: number; l: number }

const W = 520;
const H = 220;

function bar(open: number, close: number, wiggle: number): Bar {
  return { o: open, c: close, h: Math.max(open, close) + 0.01 + wiggle * 0.02, l: Math.min(open, close) - 0.01 - (1 - wiggle) * 0.02 };
}

function seedBars(): Bar[] {
  const bars: Bar[] = [];
  let price = 100;
  for (let i = 0; i < 30; i++) {
    const next = price + Math.sin(i * 1.7) * 0.03 + Math.cos(i * 0.6) * 0.02;
    bars.push(bar(price, next, Math.abs(Math.sin(i * 2.3))));
    price = next;
  }
  return bars;
}

const MOODS: Array<[number, string, string, string]> = [
  [35, 'chill', 'var(--paper-3)', 'var(--ink)'],
  [55, 'shaky', 'var(--paper-3)', 'var(--ink)'],
  [75, 'risky', 'var(--accent)', 'var(--ink)'],
  [101, 'chaos', 'var(--accent-deep)', '#fff'],
];
export const mood = (risk: number) => MOODS.find(([limit]) => risk < limit)!;

/** Hero demo: a toy candle chart and risk score that tick once a second. Holds still for reduced motion. */
export default function LiveCard() {
  const [bars, setBars] = useState(seedBars);
  const [risk, setRisk] = useState(38);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const timer = window.setInterval(() => {
      setRisk((r) => Math.max(14, Math.min(88, r + Math.round((Math.random() - 0.45) * 9))));
      setBars((previous) => {
        const last = previous.at(-1)!.c;
        return [...previous.slice(1), bar(last, last + (Math.random() - 0.48) * 0.05, Math.random())];
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const lo = Math.min(...bars.map((b) => b.l));
  const hi = Math.max(...bars.map((b) => b.h));
  const pad = (hi - lo) * 0.1 || 0.05;
  const y = (v: number) => H - ((v - lo + pad) / (hi - lo + 2 * pad)) * H;
  const step = W / bars.length;
  const last = bars.at(-1)!.c;
  const change = (last / bars[0].o - 1) * 100;
  const [, label, bg, fg] = mood(risk);

  return (
    <figure className="m-0 flex flex-col gap-4 rounded-card bg-ink-4 px-7 py-[26px]">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <span className="inline-flex items-center gap-2.5 font-bold"><span className="pulse-dot size-[9px] rounded-full bg-accent" aria-hidden="true" />SIM · demo</span>
        <span className="font-display text-[34px] font-extrabold tracking-[-0.03em]">
          ${last.toFixed(2)} <span className="text-lg" style={{ color: change >= 0 ? '#b9b7b0' : 'var(--accent)' }}>{change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(2)}%</span>
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Demo candlestick chart of the simulated stock" className="block h-[220px] w-full">
        {bars.map((b, i) => {
          const x = i * step + step / 2;
          const up = b.c >= b.o;
          const top = y(Math.max(b.o, b.c));
          return (
            <g key={i} fill={up ? 'var(--fg)' : 'var(--accent)'} stroke={up ? 'var(--fg-faint)' : 'var(--accent)'}>
              <line x1={x} x2={x} y1={y(b.h)} y2={y(b.l)} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
              <rect x={x - step * 0.32} y={top} width={step * 0.64} height={Math.max(1.5, y(Math.min(b.o, b.c)) - top)} stroke="none" />
            </g>
          );
        })}
      </svg>
      <div className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between">
          <span className="text-[#b9b7b0]">risk score</span>
          <span className="inline-flex items-baseline gap-2.5">
            <span className="font-display text-[34px] font-extrabold tracking-[-0.03em]">{risk}</span>
            <span className="rounded-full px-3 py-0.5 text-[15px] font-bold" style={{ background: bg, color: fg }}>{label}</span>
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[#2e2e35]"><div className="h-2 rounded-full bg-accent transition-[width] duration-700" style={{ width: `${risk}%` }} /></div>
      </div>
      <figcaption className="text-sm text-fg-faint">a toy preview with made-up prices. the real thing is one click away.</figcaption>
    </figure>
  );
}
