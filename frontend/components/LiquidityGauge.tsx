'use client';

import React from 'react';
import { useMarketStore } from '@/store/market-store';

export default function LiquidityGauge() {
  const marketData = useMarketStore((s) => s.marketData);
  const pred = marketData?.liquidity_prediction;

  if (!pred) {
    return (
      <div className="terminal-panel">
        <div className="panel-header">
          <span className="panel-tag">LIQUIDITY STRESS</span>
          <span className="text-xs text-gray-600">NO DATA</span>
        </div>
        <div className="flex h-40 items-center justify-center font-mono text-xs text-gray-600">
          WAITING FOR MARKET STATE
        </div>
      </div>
    );
  }

  const score = pred.health_score;
  const stressScore = pred.stress_score;
  const level = pred.warning_level;
  const scenarioPhase = marketData?.scenario.phase;
  const isForecastModel = pred.method === 'trained_model' || pred.method === 'lobster_nasdaq_model';

  const colorMap: Record<string, string> = {
    safe: '#00ff41',
    caution: '#ffb800',
    warning: '#ff6600',
    critical: '#ff0040',
  };

  const color = colorMap[level] || '#00ff41';

  // SVG arc gauge
  const radius = 60;
  const circumference = Math.PI * radius; // half circle
  const progress = (score / 100) * circumference;

  return (
    <div className="terminal-panel">
      <div className="panel-header">
        <span className="panel-tag">LIQUIDITY STRESS</span>
        <span className="text-xs" style={{ color }}>
          ● {level.toUpperCase()}
        </span>
      </div>

      <div className="flex flex-col items-center py-4">
        {/* Arc gauge */}
        <svg width="160" height="90" viewBox="0 0 160 90">
          {/* Background arc */}
          <path
            d="M 10 80 A 60 60 0 0 1 150 80"
            fill="none"
            stroke="#1a1a1a"
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Score arc */}
          <path
            d="M 10 80 A 60 60 0 0 1 150 80"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${progress} ${circumference}`}
            style={{
              filter: `drop-shadow(0 0 6px ${color})`,
              transition: 'stroke-dasharray 0.5s ease, stroke 0.5s ease',
            }}
          />
          {/* Score text */}
          <text
            x="80"
            y="70"
            textAnchor="middle"
            fill={color}
            fontSize="28"
            fontFamily="'JetBrains Mono', monospace"
            fontWeight="bold"
          >
            {score.toFixed(0)}
          </text>
          <text
            x="80"
            y="85"
            textAnchor="middle"
            fill="#666"
            fontSize="10"
            fontFamily="'JetBrains Mono', monospace"
          >
            HEALTH
          </text>
        </svg>

        {/* Stats row */}
        <div className="grid grid-cols-2 gap-4 w-full mt-3 px-2">
          <div className="stat-cell">
            <span className="stat-label">
              {isForecastModel ? 'FORECAST RISK' : 'CURRENT STRESS'}
            </span>
            <span className="stat-value" style={{ color }}>
              {(stressScore * 100).toFixed(1)}%
            </span>
          </div>
          <div className="stat-cell">
            <span className="stat-label">SCORE</span>
            <span className="stat-value" style={{ color }}>
              {score.toFixed(1)}
            </span>
          </div>
        </div>

        {/* Feature breakdown */}
        <div className="mt-2 font-mono text-[10px] tracking-[0.12em] text-gray-600">
          {isForecastModel
            ? pred.method === 'lobster_nasdaq_model'
              ? `${pred.market ?? 'NASDAQ'} MODEL`
              : `${pred.horizon_seconds}S MODEL`
            : pred.method === 'calibrating'
              ? 'CALIBRATING SESSION BASELINE'
              : 'ADAPTIVE ORDER-BOOK DIAGNOSTIC'}
        </div>
        {scenarioPhase && scenarioPhase !== 'ACTIVE' ? (
          <div className="mt-1 font-mono text-[10px] tracking-[0.12em]" style={{ color }}>
            {scenarioPhase}
          </div>
        ) : null}

        {pred.features && (
          <div className="w-full mt-3 px-2">
            <div className="text-xs text-gray-600 mb-1 font-mono">FEATURES</div>
            {Object.entries(pred.features).map(([key, val]) => (
              <div key={key} className="flex justify-between text-xs font-mono py-0.5">
                <span className="text-gray-500">{key.replace(/_/g, ' ').toUpperCase()}</span>
                <span className="text-gray-300">{typeof val === 'number' ? val.toFixed(4) : val}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
