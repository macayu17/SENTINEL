'use client';

import { Panel, EmptyState } from '@/components/ui/primitives';
import { bps, int, num } from '@/lib/format';
import type { LargeOrderDetection, OrderBook } from '@/types/market';

const LEVELS = 8;

/** L2 ladder: asks above the mid, bids below, cumulative size from the touch outward. */
export default function OrderBookPanel({ book, mid, spread, flagged }: {
  book: OrderBook | undefined;
  mid: number | undefined;
  spread: number | undefined;
  flagged: LargeOrderDetection | null | undefined;
}) {
  const asks = book?.asks.slice(0, LEVELS) ?? [];
  const bids = book?.bids.slice(0, LEVELS) ?? [];
  const peak = Math.max(1, ...asks.map((l) => l.size), ...bids.map((l) => l.size));
  const cumulative = (levels: typeof asks) => {
    let running = 0;
    return levels.map((level) => (running += level.size));
  };
  const askCum = cumulative(asks);
  const bidCum = cumulative(bids);
  const isFlagged = (side: 'buy' | 'sell', price: number) =>
    flagged?.side === side && flagged.price !== undefined && Math.abs(flagged.price - price) < 1e-9;
  const spreadBps = bps(spread, mid);

  const row = (side: 'buy' | 'sell', price: number, size: number, cum: number) => {
    const hot = isFlagged(side, price);
    const fill = side === 'sell' ? (hot ? 'rgba(255,122,61,0.35)' : 'rgba(255,122,61,0.14)') : 'rgba(242,240,235,0.12)';
    return (
      <div key={`${side}-${price}`} className="relative grid grid-cols-3 py-[3px] text-[13px]">
        <span aria-hidden="true" className="absolute inset-y-0.5 right-0 rounded-[3px]" style={{ width: `${(size / peak) * 70}%`, background: fill }} />
        <span className={`relative font-semibold ${side === 'sell' ? 'text-accent' : ''}`}>{num(price, 2)}</span>
        <span className="relative text-right">{int(size)}{hot ? <span className="sr-only"> (flagged large level)</span> : null}</span>
        <span className="relative text-right text-fg-muted">{int(cum)}</span>
      </div>
    );
  };

  return (
    <Panel title="Order book · L2" caption={`${LEVELS} levels per side · tick 0.01`} className="flex-[1_1_380px]">
      {!asks.length && !bids.length ? <EmptyState>Waiting for the order book.</EmptyState> : (
        <div className="flex flex-col">
          <div className="grid grid-cols-3 py-1 text-[11px] text-fg-muted"><span>Price</span><span className="text-right">Size</span><span className="text-right">Cumulative</span></div>
          {asks.map((level, i) => ({ level, cum: askCum[i] })).reverse().map(({ level, cum }) => row('sell', level.price, level.size, cum))}
          <div className="my-0.5 flex flex-wrap justify-between gap-2 border-y border-line py-[7px] text-[13px]">
            <span className="font-bold">Mid {num(mid, 3)}</span>
            <span className="text-fg-muted">spread {num(spread, 2)} · {num(spreadBps, 1)} bps</span>
          </div>
          {bids.map((level, i) => row('buy', level.price, level.size, bidCum[i]))}
        </div>
      )}
    </Panel>
  );
}
