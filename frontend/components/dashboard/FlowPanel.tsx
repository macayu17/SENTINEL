'use client';

import { Panel } from '@/components/ui/primitives';
import { int, num, signed } from '@/lib/format';
import type { MarketUpdate } from '@/types/market';

const compactUsd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 2 });

/** Run counters, the 10 s aggressor split, signed flow buckets and the oracle reading. */
export default function FlowPanel({ data, buckets }: {
  data: MarketUpdate | null;
  buckets: Array<{ t: number; buy: number; sell: number }>;
}) {
  const flow = data?.order_flow;
  const buy = flow?.buy_volume ?? 0;
  const sell = flow?.sell_volume ?? 0;
  const total = buy + sell;
  const peak = Math.max(1, ...buckets.flatMap((b) => [b.buy, b.sell]));
  const oracle = data?.oracle;
  const counters = [
    { label: 'Orders submitted', value: int(flow?.submitted) },
    { label: 'Fills', value: int(flow?.fills) },
    { label: 'Cancellations', value: int(flow?.cancelled) },
    { label: 'Match rate', value: flow ? `${num(flow.match_rate, 0)}%` : '—' },
    { label: 'Submitted notional', value: flow?.submitted_notional != null ? compactUsd.format(flow.submitted_notional) : '—' },
    { label: 'Activity', value: data ? `${num(data.activity_multiplier, 2)}×` : '—' },
  ];

  return (
    <Panel title="Order flow" caption="counters: whole run · aggressor volume: last 10 s" className="flex-[1_1_380px]">
      <dl className="m-0 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {counters.map((item) => (
          <div key={item.label}>
            <dt className="text-[11px] text-fg-muted">{item.label}</dt>
            <dd className="m-0 mt-0.5 font-display text-xl font-semibold">{item.value}</dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between text-xs text-fg-muted"><span>Aggressor buy volume</span><span>Aggressor sell volume</span></div>
        <div className="flex h-2.5 gap-[3px] overflow-hidden rounded-[5px]" aria-hidden="true">
          {total ? <>
            <span className="rounded-[5px] bg-fg" style={{ width: `${(buy / total) * 100}%` }} />
            <span className="rounded-[5px] bg-accent" style={{ width: `${(sell / total) * 100}%` }} />
          </> : <span className="w-full rounded-[5px] bg-line" />}
        </div>
        <div className="flex justify-between text-[13px] font-semibold">
          <span>{int(buy)} · {total ? Math.round((buy / total) * 100) : 0}%</span>
          <span>{int(sell)} · {total ? Math.round((sell / total) * 100) : 0}%</span>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-xs text-fg-muted">Aggressor volume per 5 s bucket (buy up, sell down)</span>
        <div role="img" aria-label={`Aggressor buy and sell volume over the last ${buckets.length} five-second buckets`} className="grid h-[90px] gap-0.5" style={{ gridTemplateColumns: `repeat(24, minmax(0, 1fr))` }}>
          {buckets.map((bucket) => (
            <div key={bucket.t} className="flex h-[90px] flex-col">
              <div className="flex flex-1 items-end"><div className="w-full rounded-t-sm bg-fg-2" style={{ height: `${(bucket.buy / peak) * 100}%` }} /></div>
              <div className="flex flex-1 items-start"><div className="w-full rounded-b-sm bg-accent" style={{ height: `${(bucket.sell / peak) * 100}%` }} /></div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 border-t border-line pt-2.5 text-[13px]">
        {oracle?.fundamental_value != null ? <>
          <div><span className="block text-[11px] text-fg-muted">Fundamental value</span><span className="font-semibold">{num(oracle.fundamental_value, 3)}</span></div>
          <div><span className="block text-[11px] text-fg-muted">Mispricing</span><span className="font-semibold">{signed((oracle.mispricing_pct ?? 0) * 100, 1, ' bps')}</span></div>
          <div><span className="block text-[11px] text-fg-muted">Oracle noise σ</span><span className="font-semibold">{num(oracle.observation_noise, 3)}</span></div>
        </> : <p className="col-span-3 m-0 text-fg-muted">Fundamental value hidden: informed access is off for this run.</p>}
      </div>
    </Panel>
  );
}
