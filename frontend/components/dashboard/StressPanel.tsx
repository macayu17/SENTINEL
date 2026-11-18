'use client';

import StressMeter from '@/components/ui/StressMeter';
import { EmptyState, Facts, Meter, Panel, Term } from '@/components/ui/primitives';
import { int, num, pct } from '@/lib/format';
import { FEATURE_GLOSSARY, TERM_GLOSSARY } from '@/lib/glossary';
import type { LargeOrderDetection, LiquidityPrediction } from '@/types/market';

/** Is this feature reading in the direction that means trouble? Each feature knows its own direction. */
function alarming(key: string, value: number): boolean {
  return FEATURE_GLOSSARY[key]?.alarm?.(value) ?? false;
}

const fact = (label: string) => TERM_GLOSSARY[label];

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
            <Term
              label="Feature inputs (vs trailing median)"
              title="What the model is reading"
              info="Each line is one number the model reads every second, mostly today's value divided by its own recent normal, so 1.00 means normal. Orange means that reading points towards stress. Hover any i for what it measures."
              className="text-xs text-fg-muted"
            />
            {Object.entries(prediction.features).map(([key, value]) => {
              const share = Number.isFinite(value) ? barShare(key, value) : null;
              return (
                <div key={key} className="grid grid-cols-[minmax(0,164px)_1fr_64px] items-center gap-2.5 text-[13px]">
                  <Term label={key} title={FEATURE_GLOSSARY[key]?.name} info={FEATURE_GLOSSARY[key]?.info} className="text-fg-2" />
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
          <Term label="Large order detection" title="Large order detection" info="Flags a single price level in the visible book that is far bigger than the others: often a big institution parking an order, or a spoofer showing size it does not mean to trade." className="text-[13px] font-semibold" />
          <span className="text-xs text-fg-muted">visible_order_book</span>
        </div>
        {detection ? (
          <Facts items={[
            { label: 'Side · price', value: `${detection.side.toUpperCase()} ${num(detection.price, 3)}`, accent: detection.side === 'sell', info: fact('Side · price') },
            { label: 'Est. size', value: int(detection.estimated_size), info: fact('Est. size') },
            { label: 'Size multiple', value: `${num(detection.size_multiple, 1)}× median`, info: fact('Size multiple') },
            { label: 'Depth share', value: `${pct(detection.depth_share)} of ${detection.side === 'sell' ? 'asks' : 'bids'}`, info: fact('Depth share') },
            { label: 'Confidence', value: num(detection.confidence), info: fact('Confidence') },
            { label: 'Pattern', value: detection.pattern, info: fact('Pattern') },
          ]} />
        ) : <p className="m-0 text-[13px] text-fg-muted">No outsized visible level on either side.</p>}
      </div>
    </Panel>
  );
}
