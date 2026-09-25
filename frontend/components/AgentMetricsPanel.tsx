'use client';
import { useState } from 'react';
import { useMarketStore } from '@/store/market-store';

export default function AgentMetricsPanel() {
  const marketData = useMarketStore(s => s.marketData);
  const [filter, setFilter] = useState('all');
  const symbol = marketData?.market === 'NASDAQ' ? '$' : '₹';
  const agents = Object.entries(marketData?.agent_metrics ?? {}).sort((a,b) => a[1].agent_type.localeCompare(b[1].agent_type) || b[1].total_pnl-a[1].total_pnl);
  const shown = agents.filter(([,a]) => filter === 'all' || (filter === 'halted' ? a.halted : !a.halted));
  const money = (n: number) => Number.isFinite(n) ? `${n >= 0 ? '+' : '−'}${symbol}${Math.abs(n).toFixed(2)}` : '—';
  return <details className="agent-ledger" open>
    <summary><h2>Agent ledger · {agents.length} participants</h2></summary>
    <div className="section-heading"><span>Participant positions and results</span><label>State <select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All agents</option><option value="active">Active</option><option value="halted">Halted</option></select></label></div>
    <div className="table-scroll"><table className="research-table"><thead><tr>{['AGENT','TYPE','STATE','POSITION','REALIZED','UNREALIZED','TOTAL P&L','TRADES'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{shown.map(([id,a])=><tr key={id}><td>{id}</td><td>{a.agent_type}</td><td>{a.halted ? 'Halted' : 'Active'}</td><td>{a.position.toLocaleString()}</td><td>{money(a.realized_pnl)}</td><td>{money(a.unrealized_pnl)}</td><td className={a.total_pnl < 0 ? 'negative' : 'positive'}>{money(a.total_pnl)}</td><td>{a.num_trades.toLocaleString()}</td></tr>)}</tbody></table></div>
    {!shown.length && <div className="empty-state">{agents.length ? 'No agents match this state.' : 'Agent activity will appear when an experiment starts.'}</div>}
  </details>;
}
