'use client';
import { useMarketStore } from '@/store/market-store';

export default function LiquidityGauge() {
  const marketData = useMarketStore(s=>s.marketData);
  const pred = marketData?.liquidity_prediction;
  if (!pred) return <section className="signal-section"><h2>Liquidity condition</h2><div className="empty-state">Waiting for market state.</div></section>;
  const forecast = pred.method === 'trained_model' || pred.method === 'lobster_nasdaq_model';
  return <section className="signal-section"><div className="section-heading"><h2>Liquidity condition</h2><span className={pred.warning_level === 'safe' ? 'positive' : 'negative'}>{pred.warning_level}</span></div>
    <div className="signal-score">{pred.health_score.toFixed(1)}<small> / 100 health</small></div>
    <dl className="signal-details"><div><dt>{forecast ? 'FORECAST RISK' : 'CURRENT STRESS'}</dt><dd>{(pred.stress_score*100).toFixed(1)}%</dd></div><div><dt>Method</dt><dd>{pred.method === 'calibrating' ? 'Calibrating session baseline' : forecast ? `${pred.market ?? marketData?.market ?? ''} trained model` : 'Adaptive order-book diagnostic'}</dd></div>{forecast && <div><dt>Forecast horizon</dt><dd>{pred.horizon_seconds}s</dd></div>}<div><dt>Scenario phase</dt><dd>{marketData?.scenario.phase}</dd></div>
    {Object.entries(pred.features).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{Number.isFinite(value) ? value.toFixed(4) : '—'}</dd></div>)}</dl>
  </section>;
}
