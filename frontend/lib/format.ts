import type { OrderBook, OrderLevel } from '@/types/market';

export const TICK = 0.01;
const SESSION_OPEN_SECONDS = 9.5 * 3600; // sim time 0 is the 09:30 open of a 6.5-hour session

const ok = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

export function num(value: unknown, digits = 2): string {
  return ok(value) ? value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—';
}

export function int(value: unknown): string {
  return ok(value) ? Math.round(value).toLocaleString('en-US') : '—';
}

/** Signed with a true minus sign, as the design shows: +1.20 / −0.40. */
export function signed(value: unknown, digits = 2, suffix = ''): string {
  if (!ok(value)) return '—';
  const body = Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${value < 0 ? '−' : '+'}${body}${suffix}`;
}

export function pct(value: unknown, digits = 0): string {
  return ok(value) ? `${(value * 100).toFixed(digits)}%` : '—';
}

export function bps(spread: unknown, mid: unknown): number | null {
  return ok(spread) && ok(mid) && mid > 0 ? (spread / mid) * 10_000 : null;
}

/** Sim seconds → exchange clock, e.g. 3725.4 → "10:32:05.400". */
export function sessionClock(seconds: unknown, millis = false): string {
  if (!ok(seconds)) return '—';
  const total = SESSION_OPEN_SECONDS + seconds;
  const h = Math.floor(total / 3600) % 24;
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(Math.floor(n)).padStart(2, '0');
  const ms = millis ? `.${String(Math.floor((s % 1) * 1000)).padStart(3, '0')}` : '';
  return `${pad(h)}:${pad(m)}:${pad(s)}${ms}`;
}

export function duration(seconds: unknown): string {
  if (!ok(seconds)) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m ? `${m} m ${s} s` : `${s} s`;
}

export function median(values: number[]): number | null {
  const finite = values.filter(ok).sort((a, b) => a - b);
  if (!finite.length) return null;
  const mid = finite.length >> 1;
  return finite.length % 2 ? finite[mid] : (finite[mid - 1] + finite[mid]) / 2;
}

export const sum = (levels: OrderLevel[]) => levels.reduce((total, level) => total + level.size, 0);

export interface BookStats {
  bidDepth: number;
  askDepth: number;
  /** (bid − ask) / (bid + ask): negative is a sell-heavy book. */
  imbalance: number;
  bestBid: number | null;
  bestAsk: number | null;
}

export function bookStats(book: OrderBook | undefined): BookStats {
  const bids = book?.bids ?? [];
  const asks = book?.asks ?? [];
  const bidDepth = sum(bids);
  const askDepth = sum(asks);
  return {
    bidDepth,
    askDepth,
    imbalance: bidDepth + askDepth ? (bidDepth - askDepth) / (bidDepth + askDepth) : 0,
    bestBid: bids[0]?.price ?? null,
    bestAsk: asks[0]?.price ?? null,
  };
}

/** Grouped by agent type, as the ledger and report show participants. */
export interface TypeRow { type: string; count: number; position: number; trades: number; realized: number; unrealized: number; total: number; halted: number }

export function groupByType(metrics: Record<string, { agent_type: string; position: number; num_trades: number; realized_pnl: number; unrealized_pnl: number; total_pnl: number; halted: boolean }>): TypeRow[] {
  const rows = new Map<string, TypeRow>();
  for (const agent of Object.values(metrics)) {
    const row = rows.get(agent.agent_type) ?? { type: agent.agent_type, count: 0, position: 0, trades: 0, realized: 0, unrealized: 0, total: 0, halted: 0 };
    row.count += 1;
    row.position += agent.position;
    row.trades += agent.num_trades;
    row.realized += agent.realized_pnl;
    row.unrealized += agent.unrealized_pnl;
    row.total += agent.total_pnl;
    row.halted += agent.halted ? 1 : 0;
    rows.set(agent.agent_type, row);
  }
  return [...rows.values()].sort((a, b) => b.total - a.total);
}

/** Backend warning levels, from LiquidityShockPredictor: health ≥80 safe, ≥60 caution, ≥40 warning. */
export const STRESS_BANDS = [
  { level: 'safe', from: 0 },
  { level: 'caution', from: 0.2 },
  { level: 'warning', from: 0.4 },
  { level: 'critical', from: 0.6 },
] as const;

export type WarningLevel = (typeof STRESS_BANDS)[number]['level'];

export const LEVEL_COLOR: Record<string, string> = {
  safe: 'var(--fg-muted)',
  caution: 'var(--caution)',
  warning: 'var(--accent)',
  critical: 'var(--accent)',
};
