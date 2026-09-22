'use client';
import { useMarketStore } from '@/store/market-store';

export default function LargeOrderDetector() {
  const marketData = useMarketStore(s=>s.marketData);
  const detection = marketData?.large_order_detection;
  const symbol = marketData?.market === 'NASDAQ' ? '$' : '₹';
  const bids = marketData?.order_book.bids ?? [], asks = marketData?.order_book.asks ?? [];
  const rows = detection ? [
    ['Side', detection.side],
    ['Price', detection.price === undefined ? '—' : symbol + detection.price.toFixed(3)],
    ['Confidence', (detection.confidence*100).toFixed(0)+'%'],
    ['Depth share', (detection.depth_share*100).toFixed(1)+'%'],
    ['Level multiple', detection.size_multiple.toFixed(1)+'×'],
    ['Source', 'Visible order book'],
  ] : [
    ['Book levels', String(bids.length+asks.length)],
    ['Bid depth', bids.reduce((s,l)=>s+l.size,0).toLocaleString()],
    ['Ask depth', asks.reduce((s,l)=>s+l.size,0).toLocaleString()],
    ['Top bid size', (bids[0]?.size ?? 0).toLocaleString()],
    ['Top ask size', (asks[0]?.size ?? 0).toLocaleString()],
  ];
  return <section className="signal-section"><div className="section-heading"><h2>VISIBLE LIQUIDITY</h2><span>{detection ? 'Concentrated' : marketData ? 'No outlier' : 'No data'}</span></div>
    {!marketData ? <div className="empty-state">Waiting for the order book.</div> : <><div className="signal-score">{detection ? detection.estimated_size.toLocaleString() : (bids.reduce((s,l)=>s+l.size,0)+asks.reduce((s,l)=>s+l.size,0)).toLocaleString()}<small> units</small></div><dl className="signal-details">{rows.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></>}
  </section>;
}
