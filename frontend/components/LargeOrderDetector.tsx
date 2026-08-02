'use client';

import React from 'react';
import { useMarketStore } from '@/store/market-store';

function formatPrice(value: number | undefined, symbol: string): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${symbol}${value.toFixed(2)}` : `${symbol}--`;
}

export default function LargeOrderDetector() {
  const marketData = useMarketStore((s) => s.marketData);
  const detection = marketData?.large_order_detection;
  const currencySymbol = marketData?.market === 'NASDAQ' ? '$' : '₹';

  if (!marketData || !detection) {
    const bids = marketData?.order_book.bids ?? [];
    const asks = marketData?.order_book.asks ?? [];
    const bidDepth = bids.reduce((total, level) => total + level.size, 0);
    const askDepth = asks.reduce((total, level) => total + level.size, 0);
    return (
      <div className="terminal-panel">
        <div className="panel-header">
          <span className="panel-tag">VISIBLE LIQUIDITY</span>
          <span className="text-xs text-gray-600">{marketData ? 'NO OUTLIER' : 'NO DATA'}</span>
        </div>
        {marketData ? (
          <div className="grid grid-cols-2 gap-2 p-3">
            <div className="stat-cell"><span className="stat-label">BOOK LEVELS</span><span className="stat-value text-white">{bids.length + asks.length}</span></div>
            <div className="stat-cell"><span className="stat-label">MID</span><span className="stat-value text-white">{formatPrice(marketData.price, currencySymbol)}</span></div>
            <div className="stat-cell"><span className="stat-label">BID DEPTH</span><span className="stat-value text-white">{bidDepth.toLocaleString()}</span></div>
            <div className="stat-cell"><span className="stat-label">ASK DEPTH</span><span className="stat-value text-white">{askDepth.toLocaleString()}</span></div>
            <div className="stat-cell"><span className="stat-label">TOP BID SIZE</span><span className="stat-value text-white">{(bids[0]?.size ?? 0).toLocaleString()}</span></div>
            <div className="stat-cell"><span className="stat-label">TOP ASK SIZE</span><span className="stat-value text-white">{(asks[0]?.size ?? 0).toLocaleString()}</span></div>
          </div>
        ) : (
          <div className="flex h-32 items-center justify-center text-center font-mono text-xs text-gray-600">WAITING FOR ORDER BOOK</div>
        )}
      </div>
    );
  }

  const sideColor = detection.side === 'buy' ? '#00ff41' : '#ff0040';
  return (
    <div className="terminal-panel">
      <div className="panel-header">
        <span className="panel-tag">VISIBLE LIQUIDITY</span>
        <span className="text-xs" style={{ color: sideColor }}>● CONCENTRATED</span>
      </div>
      <div className="grid grid-cols-2 gap-2 p-3">
        <div className="stat-cell"><span className="stat-label">SIDE</span><span className="stat-value" style={{ color: sideColor }}>{detection.side.toUpperCase()}</span></div>
        <div className="stat-cell"><span className="stat-label">PRICE</span><span className="stat-value text-white">{formatPrice(detection.price, currencySymbol)}</span></div>
        <div className="stat-cell"><span className="stat-label">VISIBLE SIZE</span><span className="stat-value text-white">{detection.estimated_size.toLocaleString()}</span></div>
        <div className="stat-cell"><span className="stat-label">CONFIDENCE</span><span className="stat-value text-amber-400">{(detection.confidence * 100).toFixed(0)}%</span></div>
        <div className="stat-cell"><span className="stat-label">DEPTH SHARE</span><span className="stat-value text-white">{(detection.depth_share * 100).toFixed(1)}%</span></div>
        <div className="stat-cell"><span className="stat-label">LEVEL MULTIPLE</span><span className="stat-value text-white">{detection.size_multiple.toFixed(1)}x</span></div>
      </div>
    </div>
  );
}
