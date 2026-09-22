'use client';

import React, { useEffect } from 'react';
import { useMarketStore } from '@/store/market-store';

export default function AlertBanner() {
  const alerts = useMarketStore((s) => s.alerts);
  const dismissAlert = useMarketStore((s) => s.dismissAlert);

  const activeAlerts = alerts.filter((a) => !a.dismissed);
  const latestAlert = activeAlerts[activeAlerts.length - 1];

  // Retain compatibility with caution alerts from older stored sessions.
  useEffect(() => {
    const cautions = activeAlerts.filter((a) => a.level === 'caution');
    const timers = cautions.map((a) =>
      setTimeout(() => dismissAlert(a.id), 10000)
    );
    return () => timers.forEach(clearTimeout);
  }, [activeAlerts, dismissAlert]);

  if (!latestAlert) return null;

  return (
    <div
      className="research-alert"
      role="status"
    >
      <div className="flex items-center gap-2">
        <span aria-hidden="true">●</span>
        <span className="font-bold">
          [{latestAlert.level.toUpperCase()}]
        </span>
        <span className="text-gray-300">{latestAlert.message}</span>
      </div>
      <button
        aria-label="Dismiss alert"
        onClick={() => dismissAlert(latestAlert.id)}
        className="text-gray-500 hover:text-gray-300 px-2"
      >
        ✕
      </button>
    </div>
  );
}
