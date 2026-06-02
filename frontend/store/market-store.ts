import { create } from 'zustand';
import type { Alert, MarketUpdate, SimulationMode } from '@/types/market';

type PriceHistoryPoint = {
  time: number;
  receivedAt: number;
  price: number;
  spread: number;
};

interface MarketStore {
  marketData: MarketUpdate | null;
  priceHistory: PriceHistoryPoint[];
  connected: boolean;
  alerts: Alert[];
  simulationRunning: boolean;
  simulationMode: SimulationMode;

  setMarketData: (data: MarketUpdate) => void;
  setConnected: (connected: boolean) => void;
  addAlert: (alert: Alert) => void;
  dismissAlert: (id: string) => void;
  clearAlerts: () => void;
  resetSimulationData: () => void;
  setSimulationRunning: (running: boolean) => void;
  setSimulationMode: (mode: SimulationMode) => void;
}

const MAX_PRICE_HISTORY = 240;
const MAX_ALERTS = 20;

function appendBoundedPricePoint(
  history: PriceHistoryPoint[],
  point: PriceHistoryPoint
): PriceHistoryPoint[] {
  if (history.length < MAX_PRICE_HISTORY) {
    return [...history, point];
  }
  return [...history.slice(history.length - MAX_PRICE_HISTORY + 1), point];
}

function buildNextAlerts(
  state: Pick<MarketStore, 'alerts'>,
  data: MarketUpdate,
  receivedAt: number
): Alert[] {
  const prediction = data.liquidity_prediction;
  if (
    !prediction ||
    (prediction.warning_level !== 'warning' && prediction.warning_level !== 'critical')
  ) {
    return state.alerts;
  }
  const level = prediction.warning_level;

  const existing = state.alerts.some(
    (alert) => !alert.dismissed && alert.level === level
  );
  if (existing) {
    return state.alerts;
  }

  const nextAlerts =
    state.alerts.length >= MAX_ALERTS
      ? state.alerts.slice(state.alerts.length - MAX_ALERTS + 1)
      : [...state.alerts];

  nextAlerts.push({
    id: `alert-${receivedAt}-${level}`,
    message: `Liquidity ${level.toUpperCase()}: Health ${prediction.health_score.toFixed(1)}% | Shock probability ${(prediction.probability * 100).toFixed(1)}%`,
    level,
    timestamp: data.timestamp,
    dismissed: false,
  });
  return nextAlerts;
}

export const useMarketStore = create<MarketStore>((set) => ({
  marketData: null,
  priceHistory: [],
  connected: false,
  alerts: [],
  simulationRunning: false,
  simulationMode: 'SANDBOX',

  setMarketData: (data: MarketUpdate) =>
    set((state) => {
      const receivedAt = Date.now();
      const newPoint = {
        time: data.timestamp,
        receivedAt,
        price: data.price,
        spread: data.spread,
      };
      const history = appendBoundedPricePoint(state.priceHistory, newPoint);
      const alerts = buildNextAlerts(state, data, receivedAt);

      return {
        marketData: data,
        priceHistory: history,
        alerts,
        simulationMode: data.mode,
      };
    }),

  setConnected: (connected: boolean) => set({ connected }),

  addAlert: (alert: Alert) =>
    set((state) => ({
      alerts:
        state.alerts.length >= MAX_ALERTS
          ? [...state.alerts.slice(state.alerts.length - MAX_ALERTS + 1), alert]
          : [...state.alerts, alert],
    })),

  dismissAlert: (id: string) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.id === id ? { ...a, dismissed: true } : a
      ),
    })),

  clearAlerts: () => set({ alerts: [] }),

  resetSimulationData: () =>
    set({
      marketData: null,
      priceHistory: [],
      alerts: [],
      simulationRunning: false,
      simulationMode: 'SANDBOX',
    }),

  setSimulationRunning: (running: boolean) => set({ simulationRunning: running }),

  setSimulationMode: (mode: SimulationMode) => set({ simulationMode: mode }),
}));
