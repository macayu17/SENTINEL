'use client';

import React from 'react';
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  ComposedChart,
} from 'recharts';
import { useMarketStore } from '@/store/market-store';
import type { MarketDataSource } from '@/types/market';

const IST_TIME_FORMATTER = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

function formatISTTime(timestampMs: number): string {
  if (!Number.isFinite(timestampMs)) return '--:--:--';
  return IST_TIME_FORMATTER.format(new Date(timestampMs));
}

function parseProviderTime(value?: string | null): number | null {
  if (!value) return null;
  const normalized = value.trim().replace(' ', 'T');
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(normalized);
  const timestampValue = isDateOnly ? `${normalized}T00:00:00+05:30` : normalized;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(timestampValue);
  const timestamp = Date.parse(hasZone ? timestampValue : `${timestampValue}+05:30`);
  return Number.isFinite(timestamp) ? timestamp : null;
}

function replayTimestampMs(
  pointTime: number,
  firstPointTime: number,
  source?: MarketDataSource | null,
): number | null {
  if (source?.source !== 'historical_replay') return null;
  const start = parseProviderTime(source.period_start);
  const end = parseProviderTime(source.period_end);
  if (start === null || end === null || end <= start) return null;

  const replaySteps = Math.max(1, source.replay_steps ?? source.bars ?? 1);
  const progress = Math.min(1, Math.max(0, (pointTime - firstPointTime) / replaySteps));
  return start + (end - start) * progress;
}

function formatChartTime(timestampMs: number): string {
  return formatISTTime(timestampMs);
}

function providerTimestampMs(
  point: { time: number; receivedAt: number; providerTimestamp?: string | null },
  firstPointTime: number,
  source?: MarketDataSource | null,
): number {
  if (source?.source === 'historical_replay') {
    return replayTimestampMs(point.time, firstPointTime, source) ?? point.receivedAt;
  }
  if (source?.source === 'live_depth' || source?.source === 'live_ltp') {
    return parseProviderTime(point.providerTimestamp) ?? point.receivedAt;
  }
  return point.receivedAt;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; dataKey: string; color: string }>;
  label?: number;
}

function TerminalTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload) return null;
  return (
    <div className="bg-black border border-gray-700 px-2 py-1 font-mono text-xs">
      <div className="text-gray-500">{formatChartTime(label || 0)} IST</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color }}>
          {p.dataKey.toUpperCase()}: {typeof p.value === 'number' ? p.value.toFixed(4) : p.value}
        </div>
      ))}
    </div>
  );
}

export default function PriceChart() {
  const priceHistory = useMarketStore((s) => s.priceHistory);
  const marketData = useMarketStore((s) => s.marketData);
  const dataSource = marketData?.data_source ?? null;
  const firstPointTime = priceHistory[0]?.time ?? 0;
  const chartData = priceHistory.map((point) => ({
    ...point,
    chartTimeMs: providerTimestampMs(point, firstPointTime, dataSource),
  }));

  const currentPrice = marketData?.price ?? 0;
  const priceChange = priceHistory.length > 1
    ? currentPrice - priceHistory[0].price
    : 0;
  const pctChange = priceHistory.length > 1 && priceHistory[0].price > 0
    ? (priceChange / priceHistory[0].price) * 100
    : 0;

  const changeColor = priceChange >= 0 ? '#00ff41' : '#ff0040';

  return (
    <div className="terminal-panel">
      <div className="panel-header">
        <div className="flex items-center gap-3">
          <span className="panel-tag">PRICE</span>
          <span className="text-[10px] font-mono tracking-[0.14em] text-gray-500">
            GREEN = MID PRICE
          </span>
          <span className="text-[10px] font-mono tracking-[0.14em] text-amber-500/80">
            AMBER = BID-ASK SPREAD
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-lg font-mono font-bold text-white">
            ${currentPrice.toFixed(2)}
          </span>
          <span className="text-xs font-mono" style={{ color: changeColor }}>
            {priceChange >= 0 ? '▲' : '▼'} {Math.abs(priceChange).toFixed(4)} ({pctChange.toFixed(2)}%)
          </span>
        </div>
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
            <CartesianGrid
              strokeDasharray="1 4"
              stroke="#1a1a1a"
              vertical={false}
            />
            <XAxis
              dataKey="chartTimeMs"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={formatChartTime}
              stroke="#333"
              tick={{ fill: '#555', fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }}
              interval="preserveStartEnd"
            />
            <YAxis
              yAxisId="price"
              domain={['auto', 'auto']}
              stroke="#333"
              tick={{ fill: '#555', fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }}
              tickFormatter={(v: number) => `$${v.toFixed(2)}`}
              width={65}
            />
            <YAxis
              yAxisId="spread"
              orientation="right"
              domain={['auto', 'auto']}
              stroke="#333"
              tick={{ fill: '#444', fontSize: 9, fontFamily: "'JetBrains Mono', monospace" }}
              tickFormatter={(v: number) => v.toFixed(3)}
              width={50}
            />
            <Tooltip content={<TerminalTooltip />} />

            <Area
              yAxisId="spread"
              type="monotone"
              dataKey="spread"
              fill="rgba(255, 184, 0, 0.05)"
              stroke="rgba(255, 184, 0, 0.3)"
              strokeWidth={1}
            />

            {/* Price line */}
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="price"
              stroke="#00ff41"
              strokeWidth={1.5}
              dot={false}
              animationDuration={0}
              style={{ filter: 'drop-shadow(0 0 3px rgba(0, 255, 65, 0.4))' }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Bottom stats bar */}
      <div className="flex justify-between px-3 py-1 border-t border-gray-800 text-xs font-mono">
        <span className="text-gray-500">SPREAD: <span className="text-amber-400">{marketData?.spread?.toFixed(4) ?? '—'}</span></span>
        <span className="text-gray-500">DEPTH: <span className="text-cyan-400">{marketData?.depth?.toLocaleString() ?? '—'}</span></span>
        <span className="text-gray-500">VOL: <span className="text-purple-400">{marketData?.volatility?.toFixed(4) ?? '—'}</span></span>
        <span className="text-gray-500">STEP: <span className="text-gray-300">{marketData?.step?.toLocaleString() ?? '—'}</span></span>
      </div>
    </div>
  );
}
