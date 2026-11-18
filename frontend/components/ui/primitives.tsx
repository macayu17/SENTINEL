'use client';

import { useId, type ReactNode } from 'react';

/** Rounded dark card with an h2 title and an optional caption on the right. */
export function Panel({ title, caption, actions, children, className = '', flush = false }: {
  title: string;
  caption?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Drop the inner padding, for tables that run edge to edge. */
  flush?: boolean;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={`min-w-0 rounded-panel bg-ink-2 ${flush ? 'overflow-hidden' : 'flex flex-col gap-3 px-[18px] py-4'} ${className}`}>
      <div className={`flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 ${flush ? 'border-b border-line px-[18px] py-3' : ''}`}>
        <h2 id={id} className="m-0 text-[15px] font-semibold">{title}</h2>
        {caption ? <span className="text-xs text-fg-muted">{caption}</span> : null}
        {actions}
      </div>
      {children}
    </section>
  );
}

/** KPI strip: cells separated by 1px rules. */
export function StatGrid({ label, min = 150, children }: { label: string; min?: number; children: ReactNode }) {
  return (
    <section aria-label={label} className="grid gap-px overflow-hidden rounded-panel bg-line" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${min}px), 1fr))` }}>
      {children}
    </section>
  );
}

export function Stat({ label, value, note, alert = false, size = 22 }: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  /** Tint the note orange: this reading is the reason to look. */
  alert?: boolean;
  size?: number;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 bg-ink-2 px-3.5 py-3">
      <span className="text-xs text-fg-muted">{label}</span>
      <span className="truncate font-display font-semibold tracking-[-0.01em]" style={{ fontSize: size }}>{value}</span>
      {note ? <span className={`truncate text-xs ${alert ? 'text-accent' : 'text-fg-muted'}`}>{note}</span> : null}
    </div>
  );
}

/** Segmented control. role="radio" for settings, role="tab" for view switches. */
export function Segmented<T extends string>({ label, options, value, onChange, role = 'radio', size = 'md' }: {
  label: string;
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
  role?: 'radio' | 'tab';
  size?: 'sm' | 'md';
}) {
  return (
    <div role={role === 'tab' ? 'tablist' : 'radiogroup'} aria-label={label} className="flex w-fit max-w-full gap-0.5 overflow-x-auto rounded-[10px] bg-ink-3 p-[3px]">
      {options.map((option) => {
        const on = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role={role}
            aria-checked={role === 'radio' ? on : undefined}
            aria-selected={role === 'tab' ? on : undefined}
            onClick={() => onChange(option.value)}
            className={`shrink-0 rounded-lg border-0 px-3 font-semibold ${size === 'sm' ? 'min-h-[30px] min-w-[44px] text-xs' : 'min-h-[34px] text-[13px]'} ${on ? 'bg-line-strong text-fg' : 'bg-transparent text-fg-muted'}`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** Thin horizontal bar; `value` is a 0–1 share of the track. */
export function Meter({ value, color = 'var(--fg-2)', height = 6 }: { value: number; color?: string; height?: number }) {
  const width = `${Math.max(0, Math.min(1, value)) * 100}%`;
  return (
    <span className="block overflow-hidden rounded-full bg-line" style={{ height }} aria-hidden="true">
      <span className="block h-full rounded-full" style={{ width, background: color }} />
    </span>
  );
}

export function Switch({ label, checked, onChange }: { label: string; checked: boolean; onChange: (next: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`flex h-[26px] w-[46px] flex-none rounded-full border-0 p-[3px] ${checked ? 'justify-end bg-accent' : 'justify-start bg-line-strong'}`}
    >
      <span className="size-5 rounded-full bg-fg" />
    </button>
  );
}

export function StatusDot({ live, label }: { live: boolean; label: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 text-[13px] font-semibold" role="status">
      <span className="size-2 rounded-full" style={{ background: live ? 'var(--accent)' : '#7a7a82' }} aria-hidden="true" />
      {label}
    </span>
  );
}

/** Label / value pairs in a grid. */
export function Facts({ items, columns = 3 }: { items: Array<{ label: string; value: ReactNode; accent?: boolean }>; columns?: number }) {
  return (
    <dl className="m-0 grid gap-3" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-[11px] text-fg-muted">{item.label}</dt>
          <dd className={`m-0 truncate font-semibold ${item.accent ? 'text-accent' : ''}`}>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="m-0 rounded-[10px] border border-dashed border-line px-4 py-8 text-center text-[13px] text-fg-muted">{children}</p>;
}
