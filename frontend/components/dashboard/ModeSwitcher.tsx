'use client';

import { useState } from 'react';
import { api } from '@/lib/api-client';

export default function ModeSwitcher({ currentMode }: { currentMode: string }) {
  const [loading, setLoading] = useState(false);

  const handleSwitchMode = async (mode: 'SIMULATION' | 'LIVE_SHADOW') => {
    setLoading(true);
    try {
      await api.setSimulationMode(mode);
      // Wait a moment for mode to switch safely
      await new Promise(r => setTimeout(r, 500));
      await api.startSimulation();
    } catch (err) {
      console.error('Failed to switch mode:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-3 flex gap-2 w-full justify-start border-t border-[var(--line-soft)] pt-3">
      <button
        onClick={() => handleSwitchMode('SIMULATION')}
        disabled={loading || currentMode === 'SIMULATION'}
        className={`px-3 py-1.5 text-[11px] uppercase tracking-wider font-semibold rounded-md border transition-colors ${
          currentMode === 'SIMULATION'
            ? 'bg-[var(--sky)] text-black border-transparent'
            : 'bg-[var(--card-elevated)] text-[var(--text-soft)] border-[var(--line-soft)] hover:border-[var(--sky)] hover:text-[var(--text-strong)]'
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        Simulated Market
      </button>
      <button
        onClick={() => handleSwitchMode('LIVE_SHADOW')}
        disabled={loading || currentMode === 'LIVE_SHADOW'}
        className={`px-3 py-1.5 text-[11px] uppercase tracking-wider font-semibold rounded-md border transition-colors ${
          currentMode === 'LIVE_SHADOW'
            ? 'bg-[var(--mint)] text-black border-transparent'
            : 'bg-[var(--card-elevated)] text-[var(--text-soft)] border-[var(--line-soft)] hover:border-[var(--mint)] hover:text-[var(--text-strong)]'
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        Real Market Live
      </button>
    </div>
  );
}
