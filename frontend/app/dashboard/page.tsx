'use client';

import React, { useState, useEffect } from 'react';
import { useMarketWebSocket } from '@/lib/websocket';
import { useMarketStore } from '@/store/market-store';
import { api } from '@/lib/api-client';
import PriceChart from '@/components/PriceChart';
import OrderBookHeatmap from '@/components/OrderBookHeatmap';
import LiquidityGauge from '@/components/LiquidityGauge';
import LargeOrderDetector from '@/components/LargeOrderDetector';
import AgentMetricsPanel from '@/components/AgentMetricsPanel';
import AlertBanner from '@/components/AlertBanner';

export default function DashboardPage() {
  useMarketWebSocket();

  const connected = useMarketStore((s) => s.connected);
  const marketData = useMarketStore((s) => s.marketData);
  const simulationRunning = useMarketStore((s) => s.simulationRunning);
  const setSimulationRunning = useMarketStore((s) => s.setSimulationRunning);
  const simulationMode = useMarketStore((s) => s.simulationMode);

  const [currentTime, setCurrentTime] = useState<string>('');

  useEffect(() => {
    setCurrentTime(new Date().toLocaleTimeString());
    const timer = setInterval(() => setCurrentTime(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(timer);
  }, []);

  const handleStartStop = async () => {
    try {
      if (simulationRunning) {
        await api.stopSimulation();
        setSimulationRunning(false);
      } else {
        await api.startSimulation();
        setSimulationRunning(true);
      }
    } catch (error) {
      console.error('Simulation control error:', error);
    }
  };

  const handleModeToggle = async () => {
    const newMode = simulationMode === 'SANDBOX' ? 'LIVE_SHADOW' : 'SANDBOX';
    try {
      await api.setSimulationMode(newMode);
    } catch (error) {
      console.error('Failed to change mode:', error);
    }
  };

  const formatTimestamp = (ts: number) => {
    const h = Math.floor(ts / 3600);
    const m = Math.floor((ts % 3600) / 60);
    const s = Math.floor(ts % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-black text-white font-mono">
      {/* ── Alert Banner ─── */}
      <AlertBanner />

      {/* ── Top Header Bar ─── */}
      <header className="border-b border-gray-800 px-4 py-2">
        <div className="flex items-center justify-between">
          {/* Left: Logo + Title */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-amber-400 rotate-45" />
              <span className="text-sm font-bold tracking-widest text-amber-400">
                SENTINEL
              </span>
            </div>
            <span className="text-xs text-gray-600 hidden sm:inline">
              SMART EARLY-WARNING NETWORK FOR TRADING
            </span>
          </div>

          {/* Center: Market Info */}
          <div className="flex items-center gap-4 text-xs">
            {marketData && (
              <>
                <span className="text-gray-500">
                  SIM TIME:{' '}
                  <span className="text-gray-300">
                    {formatTimestamp(marketData.timestamp)}
                  </span>
                </span>
                <span className="text-gray-500">
                  STEP:{' '}
                  <span className="text-gray-300">
                    {marketData.step.toLocaleString()}
                  </span>
                </span>
              </>
            )}
          </div>

          {/* Right: Connection + Controls */}
          <div className="flex items-center gap-3">
            {/* Connection status */}
            <div className="flex items-center gap-1.5 text-xs">
              <span
                className={connected ? 'blink' : ''}
                style={{ color: connected ? '#00ff41' : '#ff0040' }}
              >
                ●
              </span>
              <span className="text-gray-500">
                {connected ? 'CONNECTED' : 'DISCONNECTED'}
              </span>
            </div>

            {/* Mode toggle button */}
            <button
              onClick={handleModeToggle}
              className="px-3 py-1 text-xs font-mono font-bold border transition-all duration-200"
              style={{
                borderColor: simulationMode === 'SANDBOX' ? '#00ff41' : '#ffb000',
                color: simulationMode === 'SANDBOX' ? '#00ff41' : '#ffb000',
                backgroundColor: simulationMode === 'SANDBOX'
                  ? 'rgba(0, 255, 65, 0.1)'
                  : 'rgba(255, 176, 0, 0.1)',
              }}
            >
              {simulationMode === 'SANDBOX' ? 'MODE: SANDBOX' : 'MODE: LIVE'}
            </button>

            {/* Sim control button */}
            <button
              onClick={handleStartStop}
              className="px-3 py-1 text-xs font-mono font-bold border transition-all duration-200"
              style={{
                borderColor: simulationRunning ? '#ff0040' : '#00ff41',
                color: simulationRunning ? '#ff0040' : '#00ff41',
                backgroundColor: simulationRunning
                  ? 'rgba(255, 0, 64, 0.1)'
                  : 'rgba(0, 255, 65, 0.1)',
              }}
            >
              {simulationRunning ? '■ STOP' : '▶ START'}
            </button>
          </div>
        </div>
      </header>

      {/* ── Main Grid ─── */}
      <main className="p-2 grid grid-cols-12 gap-2 min-h-[calc(100vh-44px)]">
        {/* Top Row: Liquidity Gauge + Large Order Detector */}
        <div className="col-span-12 lg:col-span-3">
          <LiquidityGauge />
        </div>
        <div className="col-span-12 lg:col-span-3">
          <LargeOrderDetector />
        </div>
        <div className="col-span-12 lg:col-span-6">
          <PriceChart />
        </div>

        {/* Bottom Row: Order Book + Agent Metrics */}
        <div className="col-span-12 lg:col-span-4">
          <OrderBookHeatmap />
        </div>
        <div className="col-span-12 lg:col-span-8">
          <AgentMetricsPanel />
        </div>
      </main>

      {/* ── Status Bar ─── */}
      <footer className="fixed bottom-0 left-0 right-0 border-t border-gray-800 bg-black px-4 py-1 flex justify-between text-xs font-mono text-gray-600 z-50">
        <span>SENTINEL v2.0</span>
        <span>
          {marketData
            ? `$${marketData.price.toFixed(2)} | SPR ${marketData.spread.toFixed(4)} | DEPTH ${marketData.depth.toLocaleString()} | VOL ${marketData.volatility.toFixed(4)}`
            : 'AWAITING DATA...'}
        </span>
        <span>{currentTime}</span>
      </footer>
    </div>
  );
}
