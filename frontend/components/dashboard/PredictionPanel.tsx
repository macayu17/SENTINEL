import SectionCard from '@/components/dashboard/SectionCard';
import { PredictionSignal } from '@/types/dashboard';

interface PredictionPanelProps {
  prediction: PredictionSignal;
  mode: 'SIMULATION' | 'LIVE_SHADOW';
}

function signalStyle(signal: PredictionSignal['signal']): string {
  if (signal === 'BUY') return 'text-[var(--mint)] border-[var(--mint)]/35 bg-[var(--mint)]/8';
  if (signal === 'SELL') return 'text-[var(--rose)] border-[var(--rose)]/35 bg-[var(--rose)]/8';
  return 'text-[var(--gold)] border-[var(--gold)]/35 bg-[var(--gold)]/8';
}

export default function PredictionPanel({ prediction, mode }: PredictionPanelProps) {
  const confidencePct = Math.round(prediction.confidence * 100);

  return (
    <SectionCard
      title="Prediction Signal"
      subtitle="Investor-facing decision support from rule-based signal engine"
      rightSlot={
        <span className={`rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.12em] ${mode === 'LIVE_SHADOW' ? 'border-[var(--sky)]/40 bg-[var(--sky)]/10 text-[var(--sky)]' : 'border-[var(--gold)]/35 bg-[var(--gold)]/10 text-[var(--gold)]'}`}>
          {mode === 'LIVE_SHADOW' ? 'Real Market Mode' : 'Simulation Mode'}
        </span>
      }
    >
      <div className="grid gap-3 md:grid-cols-[0.9fr_1.1fr]">
        <div className={`rounded-xl border p-4 ${signalStyle(prediction.signal)}`}>
          <p className="text-[11px] uppercase tracking-[0.12em] opacity-80">Current Signal</p>
          <p className="mt-1 text-3xl font-semibold leading-none">{prediction.signal}</p>
          <p className="mt-2 text-sm opacity-90">Confidence: {confidencePct}%</p>
        </div>

        <div className="rounded-xl border border-[var(--line-soft)] bg-[var(--card-elevated)] p-4">
          <p className="text-[11px] uppercase tracking-[0.12em] text-[var(--text-soft)]">Explanation</p>
          <p className="mt-2 text-sm leading-6 text-[var(--text-strong)]">{prediction.explanation}</p>
        </div>
      </div>
    </SectionCard>
  );
}
