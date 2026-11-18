'use client';

import type { Candle } from '@/lib/candles';

interface ChartCandle extends Candle { volume?: number }

const W = 1000;

/**
 * OHLC candles with optional volume bars, a running VWAP and shaded time
 * windows. The plot stretches to its box; axis labels are HTML so they never
 * distort. Rising candles are light, falling ones orange.
 */
export default function CandleChart({ candles, height = 340, shade = [], showVolume = true, showVwap = false, priceDigits = 3, timeLabel, label }: {
  candles: ChartCandle[];
  height?: number;
  /** [start, end] pairs in candle time units (ms). */
  shade?: Array<[number, number]>;
  showVolume?: boolean;
  showVwap?: boolean;
  priceDigits?: number;
  timeLabel: (time: number) => string;
  label: string;
}) {
  if (!candles.length) return null;
  const volumeBand = showVolume ? Math.round(height * 0.17) : 0;
  const priceBottom = height - volumeBand - (showVolume ? 12 : 0);
  const lows = candles.map((c) => c.low);
  const highs = candles.map((c) => c.high);
  const pad = Math.max((Math.max(...highs) - Math.min(...lows)) * 0.08, 0.005);
  const lo = Math.min(...lows) - pad;
  const hi = Math.max(...highs) + pad;
  const y = (price: number) => 8 + (1 - (price - lo) / (hi - lo)) * (priceBottom - 16);
  const step = W / Math.max(candles.length, 24);
  const body = Math.max(2, step * 0.64);
  const x = (index: number) => index * step + step / 2;
  const t0 = candles[0].time;
  const tEnd = candles.at(-1)!.time + (candles[1] ? candles[1].time - candles[0].time : 1000);
  const tx = (time: number) => ((time - t0) / Math.max(1, tEnd - t0)) * (candles.length * step);
  const maxVolume = Math.max(1, ...candles.map((c) => c.volume ?? 0));

  let up = '', down = '', wickUp = '', wickDown = '', volUp = '', volDown = '';
  let pv = 0, vv = 0;
  const vwap: string[] = [];
  candles.forEach((c, i) => {
    const rising = c.close >= c.open;
    const top = y(Math.max(c.open, c.close));
    const h = Math.max(1, y(Math.min(c.open, c.close)) - top);
    const rect = `M${(x(i) - body / 2).toFixed(1)} ${top.toFixed(1)}h${body.toFixed(1)}v${h.toFixed(1)}h${(-body).toFixed(1)}z`;
    const wick = `M${x(i).toFixed(1)} ${y(c.high).toFixed(1)}V${y(c.low).toFixed(1)}`;
    if (rising) { up += rect; wickUp += wick; } else { down += rect; wickDown += wick; }
    if (showVolume && c.volume) {
      const vh = (c.volume / maxVolume) * volumeBand;
      const bar = `M${(x(i) - body / 2).toFixed(1)} ${(height - vh).toFixed(1)}h${body.toFixed(1)}v${vh.toFixed(1)}h${(-body).toFixed(1)}z`;
      if (rising) volUp += bar; else volDown += bar;
    }
    if (showVwap && c.volume) {
      pv += ((c.high + c.low + c.close) / 3) * c.volume;
      vv += c.volume;
      vwap.push(`${x(i).toFixed(1)},${y(pv / vv).toFixed(1)}`);
    }
  });
  const ticks = [0, 1, 2, 3].map((k) => hi - ((hi - lo) * (k + 0.5)) / 4);
  const middle = candles[Math.floor((candles.length - 1) / 2)];

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex min-w-0 gap-2">
        <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" role="img" aria-label={label} className="block min-w-0 flex-1" style={{ height }}>
          {ticks.map((price) => <line key={price} x1="0" x2={W} y1={y(price)} y2={y(price)} stroke="var(--line-soft)" vectorEffect="non-scaling-stroke" />)}
          {shade.map(([start, end]) => (
            <rect key={start} x={tx(start)} width={Math.max(step, tx(end) - tx(start))} y="0" height={height} fill="var(--accent)" fillOpacity="0.08" />
          ))}
          <path d={volUp} fill="var(--line-strong)" />
          <path d={volDown} fill="var(--accent)" fillOpacity="0.45" />
          {vwap.length > 1 && <polyline points={vwap.join(' ')} fill="none" stroke="var(--fg-muted)" strokeWidth="1.2" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />}
          <path d={wickUp} stroke="var(--fg-faint)" vectorEffect="non-scaling-stroke" />
          <path d={wickDown} stroke="var(--accent)" vectorEffect="non-scaling-stroke" />
          <path d={up} fill="var(--fg)" />
          <path d={down} fill="var(--accent)" />
        </svg>
        <div className="relative w-14 flex-none text-[11px] text-fg-muted" style={{ height }} aria-hidden="true">
          {ticks.map((price) => <span key={price} className="absolute left-0 -translate-y-1/2" style={{ top: y(price) }}>{price.toFixed(priceDigits)}</span>)}
          {showVolume && <span className="absolute bottom-0 left-0">vol</span>}
        </div>
      </div>
      <div className="flex justify-between pr-16 text-xs text-fg-muted">
        <span>{timeLabel(candles[0].time)}</span>
        {candles.length > 2 && <span>{timeLabel(middle.time)}</span>}
        <span>{timeLabel(candles.at(-1)!.time)}</span>
      </div>
    </div>
  );
}
