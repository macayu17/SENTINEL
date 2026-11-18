import { LEVEL_COLOR, STRESS_BANDS, num } from '@/lib/format';

/** Big stress score, its level chip, and the four backend bands with the current one lit. */
export default function StressMeter({ stress, level, health }: { stress: number; level: string; health: number }) {
  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="font-display text-5xl font-semibold leading-none tracking-[-0.02em]">{num(stress)}</span>
        <LevelChip level={level} />
        <span className="text-[13px] text-fg-muted">health {num(health / 100)}</span>
      </div>
      <div className="grid grid-cols-4 gap-[3px]" aria-label={`Stress bands; current level ${level}`}>
        {STRESS_BANDS.map((band) => {
          const current = band.level === level;
          return (
            <div key={band.level} className="flex flex-col gap-1">
              <span className="h-1.5 rounded-sm" style={{ background: current ? LEVEL_COLOR[band.level] : 'var(--line)' }} />
              <span className={`text-[11px] ${current ? 'font-semibold text-fg' : 'text-fg-muted'}`}>
                {band.level}{band.from ? ` ${band.from.toFixed(2)}` : ''}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function LevelChip({ level }: { level: string }) {
  const raised = level === 'warning' || level === 'critical';
  return (
    <span
      className="rounded-md px-2.5 py-[3px] text-xs font-bold uppercase tracking-[0.06em]"
      style={{
        background: raised ? 'var(--accent-chip)' : 'var(--ink-3)',
        color: raised ? 'var(--accent)' : level === 'caution' ? 'var(--caution)' : 'var(--fg-muted)',
      }}
    >
      {level}
    </span>
  );
}
