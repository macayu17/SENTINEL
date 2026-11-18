'use client';

import StressMeter from '@/components/ui/StressMeter';
import { EmptyState, Facts, Meter, Panel } from '@/components/ui/primitives';
import { int, num, pct } from '@/lib/format';
import type { LargeOrderDetection, LiquidityPrediction } from '@/types/market';

/** Is this feature reading in the direction that means trouble? */
function alarming(key: string, value: number): boolean {
  if (key === 'depth_ratio') return value < 0.6;
  if (key.endsWith('_ratio')) return value > 1.5;
  if (/depletion|expansion|pressure|stress/.test(key)) return value > 0.5;
  return false;
}

/** Bars only where the value lives on a comparable 0–1 (or 0–2 for ratios) scale. */
function barShare(key: string, value: number): number | null {
  if (key.endsWith('_ratio') && value >= 0 && value <= 4) return value / 2;
  if (value >= 0 && value <= 1) return value;
  return null;
}

export default function StressPanel({ prediction, detection }: {
  prediction: LiquidityPrediction | null | undefined;
  detection: LargeOrderDetection | null | undefined;
}) {
  const horizon = prediction?.horizon_seconds ? `horizon ${prediction.horizon_seconds} s` : 'current state';
  return (
    <Panel title="Liquidity stress" caption={prediction ? `${horizon} · ${prediction.method}` : undefined} className="flex-[1_1_340px] !gap-3.5">
      {!prediction ? <EmptyState>Waiting for the first detector reading.</EmptyState> : (
        <>
          <StressMeter stress={prediction.stress_score} level={prediction.warning_level} health={prediction.health_score} />
          <div className="flex flex-col gap-2 border-t border-line pt-3">
            <span className="text-xs text-fg-muted">Feature inputs (vs trailing median)</span>
            {Object.entries(prediction.features).map(([key, value]) => {
              const share = Number.isFinite(value) ? barShare(key, value) : null;
              return (
                <div key={key} className="grid grid-cols-[minmax(0,140px)_1fr_64px] items-center gap-2.5 text-[13px]">
                  <span className="truncate text-fg-2">{key}</span>
                  {share === null ? <span /> : <Meter value={share} color={alarming(key, value) ? 'var(--accent)' : 'var(--fg-2)'} />}
                  <span className="text-right font-semibold">{Math.abs(value) >= 100 ? int(value) : num(value)}</span>
                </div>
              );
            })}
          </div>
        </>
      )}
      <div className="flex flex-col gap-1.5 border-t border-line pt-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[13px] font-semibold">Large order detection</span>
          <span className="text-xs text-fg-muted">visible_order_book</span>
        </div>
        {detection ? (
          <Facts items={[
            { label: 'Side · price', value: `${detection.side.toUpperCase()} ${num(detection.price, 3)}`, accent: detection.side === 'sell' },
            { label: 'Est. size', value: int(detection.estimated_size) },
            { label: 'Size multiple', value: `${num(detection.size_multiple, 1)}× median` },
            { label: 'Depth share', value: `${pct(detection.depth_share)} of ${detection.side === 'sell' ? 'asks' : 'bids'}` },
            { label: 'Confidence', value: num(detection.confidence) },
            { label: 'Pattern', value: detection.pattern },
          ]} />
        ) : <p className="m-0 text-[13px] text-fg-muted">No outsized visible level on either side.</p>}
      </div>
    </Panel>
  );
}
