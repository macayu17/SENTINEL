'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useMarketStore } from '@/store/market-store';
import type { MarketUpdate } from '@/types/market';
import { getWsBaseUrl } from '@/lib/runtime-config';

const MAX_RETRIES = 5;

type FlushHandle =
  | { kind: 'frame'; id: number }
  | { kind: 'timer'; id: ReturnType<typeof setTimeout> };

function finiteNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function normalizeMarketUpdate(data: Partial<MarketUpdate>): MarketUpdate {
  return {
    type: 'market_update',
    market: data.market ?? 'NASDAQ',
    venue: data.venue ?? data.market ?? 'NASDAQ',
    timestamp: finiteNumber(data.timestamp, 0),
    price: finiteNumber(data.price, 0),
    spread: finiteNumber(data.spread, 0),
    depth: finiteNumber(data.depth, 0),
    order_book: data.order_book ?? { bids: [], asks: [] },
    liquidity_prediction: data.liquidity_prediction ?? null,
    large_order_detection: data.large_order_detection ?? null,
    agent_metrics: data.agent_metrics ?? {},
    step: finiteNumber(data.step, 0),
    volatility: finiteNumber(data.volatility, 0),
    session_phase: data.session_phase ?? 'CONTINUOUS',
    activity_multiplier: finiteNumber(data.activity_multiplier, 1),
    scenario: data.scenario ?? {
      name: 'normal',
      label: 'Normal Session',
      description: '',
      phase: 'ACTIVE',
    },
    latency_mode: data.latency_mode ?? 'DETERMINISTIC',
    data_source: data.data_source ?? null,
    events: data.events ?? [],
    order_flow: data.order_flow,
    recent_orders: data.recent_orders ?? [],
    oracle: data.oracle,
  };
}

export function useMarketWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flushHandleRef = useRef<FlushHandle | null>(null);
  const latestUpdateRef = useRef<MarketUpdate | null>(null);
  const manuallyClosedRef = useRef(false);

  const setMarketData = useMarketStore((s) => s.setMarketData);
  const setConnected = useMarketStore((s) => s.setConnected);

  const flushLatestUpdate = useCallback(() => {
    flushHandleRef.current = null;
    const update = latestUpdateRef.current;
    if (update) {
      latestUpdateRef.current = null;
      setMarketData(update);
    }
  }, [setMarketData]);

  const scheduleFlush = useCallback(() => {
    if (flushHandleRef.current) {
      return;
    }

    if (typeof window !== 'undefined' && 'requestAnimationFrame' in window) {
      flushHandleRef.current = {
        kind: 'frame',
        id: window.requestAnimationFrame(flushLatestUpdate),
      };
      return;
    }

    flushHandleRef.current = {
      kind: 'timer',
      id: setTimeout(flushLatestUpdate, 16),
    };
  }, [flushLatestUpdate]);

  const cancelScheduledFlush = useCallback(() => {
    const handle = flushHandleRef.current;
    if (!handle) {
      return;
    }

    if (handle.kind === 'frame') {
      window.cancelAnimationFrame(handle.id);
    } else {
      clearTimeout(handle.id);
    }
    flushHandleRef.current = null;
  }, []);

  const connect = useCallback(() => {
    if (
      wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    try {
      manuallyClosedRef.current = false;
      const ws = new WebSocket(`${getWsBaseUrl()}/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        retriesRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as Partial<MarketUpdate>;
          if (data.type === 'market_update') {
            latestUpdateRef.current = normalizeMarketUpdate(data);
            scheduleFlush();
          }
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;

        if (!manuallyClosedRef.current && retriesRef.current < MAX_RETRIES) {
          const delay = Math.min(1000 * Math.pow(2, retriesRef.current), 16000);
          retriesRef.current++;
          timerRef.current = setTimeout(connect, delay);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      setConnected(false);
    }
  }, [scheduleFlush, setConnected]);

  const disconnect = useCallback(() => {
    manuallyClosedRef.current = true;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    cancelScheduledFlush();
    latestUpdateRef.current = null;
    if (wsRef.current) wsRef.current.close();
    wsRef.current = null;
    setConnected(false);
  }, [cancelScheduledFlush, setConnected]);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { connect, disconnect };
}
