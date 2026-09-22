'use client';

import { useMemo, useState } from 'react';
import { useMarketStore } from '@/store/market-store';
import { aggregateCandles } from '@/lib/candles';

const clock = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const intervals = [1000, 5000, 15000];

function formatChartTime(time: number) {
  return clock.format(time);
}

export default function PriceChart() {
  const priceHistory = useMarketStore((state) => state.priceHistory);
  const marketData = useMarketStore((state) => state.marketData);
  const [interval, setInterval] = useState(5000);
  const [selected, setSelected] = useState<number | null>(null);
  const chartData = useMemo(
    () => priceHistory.map((point) => ({ ...point, chartTimeMs: point.receivedAt })),
    [priceHistory],
  );
  const candles = useMemo(
    () => aggregateCandles(chartData, interval),
    [chartData, interval],
  );
  const symbol = marketData?.market === 'NASDAQ' ? '$' : '₹';
  const current = marketData?.price;
  const change = current !== undefined && priceHistory[0]?.price > 0
    ? (current / priceHistory[0].price - 1) * 100
    : null;
  const values = candles.flatMap((candle) => [candle.high, candle.low]);
  const lowValue = Math.min(...values);
  const highValue = Math.max(...values);
  const padding = Math.max((highValue - lowValue) * 0.16, 0.005);
  const low = lowValue - padding;
  const high = highValue + padding;
  const y = (price: number) => 265 - ((price - low) / (high - low)) * 240;
  const width = 755 / Math.max(candles.length, 16);
  const inspected = selected === null ? null : candles[Math.min(selected, candles.length - 1)];

  const inspectAt = (clientX: number, element: SVGSVGElement) => {
    const rect = element.getBoundingClientRect();
    const chartX = (clientX - rect.left) / rect.width * 840;
    setSelected(Math.max(0, Math.min(candles.length - 1, Math.round((chartX - 10) / width))));
  };

  return <section className="market-chart" aria-label="Market price chart">
    <div className="market-top">
      <div className="price-quote">
        <strong>{current === undefined ? '—' : `${symbol}${current.toFixed(3)}`}</strong>
        <span className={change !== null && change < 0 ? 'negative' : 'positive'}>
          {change === null ? 'Awaiting prices' : `${change >= 0 ? '+' : ''}${change.toFixed(3)}%`}
        </span>
      </div>
      <div className="chart-periods" aria-label="Candle interval">
        {intervals.map((value) => <button key={value} aria-pressed={interval === value} onClick={() => { setInterval(value); setSelected(null); }}>{value / 1000}s</button>)}
      </div>
    </div>
    <div className="chart-caption">
      <span>OHLC candles from received mid-price samples</span>
      <span>{inspected ? `O ${inspected.open.toFixed(3)} · H ${inspected.high.toFixed(3)} · L ${inspected.low.toFixed(3)} · C ${inspected.close.toFixed(3)}` : 'Hover or use arrow keys to inspect'}</span>
    </div>
    {!candles.length ? <div className="empty-state">Start an experiment to observe prices and liquidity.</div> : <svg viewBox="0 0 840 315" tabIndex={0} role="img" aria-label="Received market prices aggregated into OHLC candles. Left and right arrows inspect values." onKeyDown={(event) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      setSelected(Math.max(0, Math.min(candles.length - 1, (selected ?? 0) + (event.key === 'ArrowRight' ? 1 : -1))));
    }} onPointerMove={(event) => inspectAt(event.clientX, event.currentTarget)} onPointerLeave={() => setSelected(null)} onBlur={() => setSelected(null)}>
      {[0, 1, 2, 3, 4].map((index) => {
        const price = low + (high - low) * index / 4;
        return <g key={index}><line x1="0" x2="775" y1={y(price)} y2={y(price)} className="chart-grid" /><text x="784" y={y(price) + 3} className="chart-label">{price.toFixed(3)}</text></g>;
      })}
      {candles.map((candle, index) => {
        const x = 10 + index * width;
        const rising = candle.close >= candle.open;
        const bodyTop = y(Math.max(candle.open, candle.close));
        const bodyBottom = y(Math.min(candle.open, candle.close));
        return <g key={candle.time} className={`ohlc-candle ${rising ? 'up' : 'down'} ${index === candles.length - 1 ? 'live' : ''}`}>
          <line className="candle-wick upper" x1={x} x2={x} y1={y(candle.high)} y2={bodyTop} />
          <rect x={x - width * 0.32} y={bodyTop} width={Math.max(5, width * 0.64)} height={Math.max(2, bodyBottom - bodyTop)} rx="1" />
          <line className="candle-wick lower" x1={x} x2={x} y1={bodyBottom} y2={y(candle.low)} />
        </g>;
      })}
      {current !== undefined && <line x1="0" x2="775" y1={y(current)} y2={y(current)} className="current-price-line" />}
      {[0, Math.floor((candles.length - 1) / 2), candles.length - 1].filter((value, index, all) => all.indexOf(value) === index && (index === 0 || (value - all[index - 1]) * width > 110)).map((index) => <text key={index} x={10 + index * width} y="300" textAnchor={index === 0 ? 'start' : 'middle'} className="chart-label">{formatChartTime(candles[index].time)}</text>)}
      {selected !== null && inspected && <line x1={10 + Math.min(selected, candles.length - 1) * width} x2={10 + Math.min(selected, candles.length - 1) * width} y1="12" y2="278" className="chart-crosshair" />}
    </svg>}
    <div className="chart-footnote" role="status">{inspected ? `${formatChartTime(inspected.time)} IST · ${symbol}${inspected.close.toFixed(3)} close` : 'New candle bodies enter smoothly; the current candle updates from the latest received price.'}</div>
  </section>;
}
