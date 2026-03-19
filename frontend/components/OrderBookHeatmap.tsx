'use client';

import React from 'react';
import { useMarketStore } from '@/store/market-store';

export default function OrderBookHeatmap() {
  const marketData = useMarketStore((s) => s.marketData);
  const orderBook = marketData?.order_book;

  const bids = orderBook?.bids ?? [];
  const asks = orderBook?.asks ?? [];

  // Find max size for scaling
  const allSizes = [...bids, ...asks].map((l) => l.size);
  const maxSize = Math.max(...allSizes, 1);

  const midPrice = marketData?.price ?? 100;

  return (
    <div className="terminal-panel">
      <div className="panel-header">
        <span className="panel-tag">ORDER BOOK</span>
        <span className="text-xs font-mono text-gray-400">
          MID: <span className="text-white">${midPrice.toFixed(2)}</span>
        </span>
      </div>

      <div className="p-2 space-y-0.5">
        {/* Asks (reversed so best ask is at bottom, near mid) */}
        <div className="text-xs font-mono text-gray-600 mb-1">ASKS</div>
        {[...asks].reverse().slice(0, 10).map((level, i) => {
          const width = (level.size / maxSize) * 100;
          return (
            <div key={`ask-${i}`} className="flex items-center gap-2 h-5">
              <span className="w-16 text-right text-xs font-mono text-red-400">
                ${level.price.toFixed(2)}
              </span>
              <div className="flex-1 relative h-full">
                <div
                  className="absolute right-0 top-0 h-full transition-all duration-300"
                  style={{
                    width: `${width}%`,
                    background: 'linear-gradient(90deg, transparent, rgba(255, 0, 64, 0.3))',
                    borderRight: '2px solid rgba(255, 0, 64, 0.6)',
                  }}
                />
              </div>
              <span className="w-14 text-right text-xs font-mono text-gray-400">
                {level.size.toLocaleString()}
              </span>
            </div>
          );
        })}

        {/* Mid-price divider */}
        <div className="flex items-center gap-2 my-1">
          <span className="w-16 text-right text-xs font-mono font-bold text-white">
            ${midPrice.toFixed(2)}
          </span>
          <div className="flex-1 border-t border-dashed border-gray-600" />
          <span className="text-xs font-mono text-gray-500">MID</span>
        </div>

        {/* Bids */}
        <div className="text-xs font-mono text-gray-600 mb-1">BIDS</div>
        {bids.slice(0, 10).map((level, i) => {
          const width = (level.size / maxSize) * 100;
          return (
            <div key={`bid-${i}`} className="flex items-center gap-2 h-5">
              <span className="w-16 text-right text-xs font-mono text-green-400">
                ${level.price.toFixed(2)}
              </span>
              <div className="flex-1 relative h-full">
                <div
                  className="absolute left-0 top-0 h-full transition-all duration-300"
                  style={{
                    width: `${width}%`,
                    background: 'linear-gradient(270deg, transparent, rgba(0, 255, 65, 0.3))',
                    borderLeft: '2px solid rgba(0, 255, 65, 0.6)',
                  }}
                />
              </div>
              <span className="w-14 text-right text-xs font-mono text-gray-400">
                {level.size.toLocaleString()}
              </span>
            </div>
          );
        })}
      </div>

      {/* Footer stats */}
      <div className="flex justify-between px-3 py-1 border-t border-gray-800 text-xs font-mono">
        <span className="text-gray-500">
          BID DEPTH:{' '}
          <span className="text-green-400">
            {bids.reduce((s, l) => s + l.size, 0).toLocaleString()}
          </span>
        </span>
        <span className="text-gray-500">
          ASK DEPTH:{' '}
          <span className="text-red-400">
            {asks.reduce((s, l) => s + l.size, 0).toLocaleString()}
          </span>
        </span>
      </div>
    </div>
  );
}
