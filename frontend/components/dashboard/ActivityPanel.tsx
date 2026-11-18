'use client';

import { useState } from 'react';
import { Panel, Segmented, EmptyState } from '@/components/ui/primitives';
import { groupByType, int, num, sessionClock, signed } from '@/lib/format';
import type { MarketUpdate } from '@/types/market';

type Tab = 'agents' | 'orders' | 'events';

const TABS: Array<{ value: Tab; label: string }> = [
  { value: 'agents', label: 'Agents' },
  { value: 'orders', label: 'Recent orders' },
  { value: 'events', label: 'Event log' },
];

const SEVERITY_COLOR: Record<string, string> = { critical: 'var(--accent)', warning: 'var(--accent)', info: 'var(--fg-muted)' };

export default function ActivityPanel({ data }: { data: MarketUpdate | null }) {
  const [tab, setTab] = useState<Tab>('agents');
  const agents = groupByType(data?.agent_metrics ?? {});
  const orders = data?.recent_orders ?? [];
  const events = data?.events ?? [];

  return (
    <Panel title="Activity" flush actions={<Segmented label="Activity view" role="tab" options={TABS} value={tab} onChange={setTab} />}>
      <div className="overflow-x-auto" role="tabpanel">
        {tab === 'agents' && (agents.length ? (
          <table className="data-table min-w-[860px]">
            <thead><tr><th scope="col">Agent type</th><th scope="col" className="num">Count</th><th scope="col" className="num">Net position</th><th scope="col" className="num">Trades</th><th scope="col" className="num">Realized PnL</th><th scope="col" className="num">Unrealized PnL</th><th scope="col" className="num">Total PnL</th><th scope="col">Status</th></tr></thead>
            <tbody>
              {agents.map((row) => (
                <tr key={row.type}>
                  <td className="font-semibold">{row.type}</td>
                  <td className="num text-fg-muted">{row.count}</td>
                  <td className="num">{signed(row.position, 0)}</td>
                  <td className="num">{int(row.trades)}</td>
                  <td className="num">{signed(row.realized)}</td>
                  <td className="num">{signed(row.unrealized)}</td>
                  <td className="num font-bold" style={{ color: row.total < 0 ? 'var(--accent)' : 'var(--fg)' }}>{signed(row.total)}</td>
                  <td style={{ color: row.halted ? 'var(--accent)' : 'var(--fg-muted)' }}>{row.halted ? `${row.halted} halted · risk limit` : 'active'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="p-4"><EmptyState>Agent results appear once a session is running.</EmptyState></div>)}

        {tab === 'orders' && (orders.length ? (
          <table className="data-table min-w-[860px]">
            <thead><tr><th scope="col">Time</th><th scope="col">Order ID</th><th scope="col">Agent</th><th scope="col">Side</th><th scope="col" className="num">Price</th><th scope="col" className="num">Qty</th><th scope="col">Status</th></tr></thead>
            <tbody>
              {orders.map((order, index) => (
                <tr key={`${order.id}-${order.status}-${index}`}>
                  <td className="text-fg-muted">{sessionClock(order.timestamp, true)}</td>
                  <td className="text-fg-muted">{order.id}</td>
                  <td>{order.agent_id}</td>
                  <td className="font-semibold" style={{ color: order.side === 'SELL' ? 'var(--accent)' : 'var(--fg)' }}>{order.side}</td>
                  <td className="num">{num(order.price, 2)}</td>
                  <td className="num">{int(order.quantity)}</td>
                  <td>{order.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="p-4"><EmptyState>No orders recorded yet.</EmptyState></div>)}

        {tab === 'events' && (events.length ? (
          <table className="data-table min-w-[860px]">
            <thead><tr><th scope="col">Time</th><th scope="col">Step</th><th scope="col">Type</th><th scope="col">Severity</th><th scope="col">Message</th></tr></thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td className="text-fg-muted">{sessionClock(event.timestamp, true)}</td>
                  <td className="text-fg-muted">{int(event.step)}</td>
                  <td>{event.type}</td>
                  <td className="font-semibold" style={{ color: SEVERITY_COLOR[event.severity] ?? 'var(--fg-muted)' }}>{event.severity}</td>
                  <td>{event.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="p-4"><EmptyState>No exchange events yet.</EmptyState></div>)}
      </div>
    </Panel>
  );
}
