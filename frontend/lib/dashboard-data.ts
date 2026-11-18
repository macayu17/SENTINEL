'use client';

import { useEffect, useState } from 'react';
import { aggregateCandles, type Candle } from '@/lib/candles';
import { bookStats, bps, median } from '@/lib/format';
import { useMarketStore } from '@/store/market-store';

/** One row per market_update, keyed by simulated time. */
export interface TapeSample {
  t: number;
  price: number;
  spreadBps: number | null;
  bidDepth: number;
  askDepth: number;
  /** Aggressor volume over the backend's trailing 10 s window. */
  buy10: number;
  sell10: number;
  fills: number;
  level: string;
  /** Shares traded since the previous sample, estimated from the 10 s window rate. */
  volume: number;
}

const MAX_SAMPLES = 1_800;
const FLOW_WINDOW_SECONDS = 10;

/** Accumulates the live feed into a rolling tape; clears when the run resets. */
export function useSessionTape(): TapeSample[] {
  const marketData = useMarketStore((state) => state.marketData);
  const [tape, setTape] = useState<TapeSample[]>([]);

  useEffect(() => {
    if (!marketData) {
      setTape([]);
      return;
    }
    setTape((previous) => {
      const last = previous.at(-1);
      if (last && marketData.timestamp <= last.t) {
        // A new run restarts the clock; anything else is a duplicate frame.
        return marketData.timestamp < last.t ? [] : previous;
      }
      const book = bookStats(marketData.order_book);
      const buy10 = marketData.order_flow?.buy_volume ?? 0;
      const sell10 = marketData.order_flow?.sell_volume ?? 0;
      const dt = last ? Math.min(FLOW_WINDOW_SECONDS, marketData.timestamp - last.t) : 0;
      const sample: TapeSample = {
        t: marketData.timestamp,
        price: marketData.price,
        spreadBps: bps(marketData.spread, marketData.price),
        bidDepth: book.bidDepth,
        askDepth: book.askDepth,
        buy10,
        sell10,
        fills: marketData.order_flow?.fills ?? 0,
        level: marketData.liquidity_prediction?.warning_level ?? 'safe',
        volume: ((buy10 + sell10) * dt) / FLOW_WINDOW_SECONDS,
      };
      const next = previous.length >= MAX_SAMPLES ? previous.slice(previous.length - MAX_SAMPLES + 1) : previous.slice();
      next.push(sample);
      return next;
    });
  }, [marketData]);

  return tape;
}

export interface VolumeCandle extends Candle { volume: number }

export function tapeCandles(tape: TapeSample[], intervalSeconds: number): VolumeCandle[] {
  const volumes = new Map<number, number>();
  for (const sample of tape) {
    const bucket = Math.floor(sample.t / intervalSeconds) * intervalSeconds * 1000;
    volumes.set(bucket, (volumes.get(bucket) ?? 0) + sample.volume);
  }
  return aggregateCandles(
    tape.map((sample) => ({ receivedAt: sample.t * 1000, price: sample.price })),
    intervalSeconds * 1000,
  ).map((candle) => ({ ...candle, volume: volumes.get(candle.time) ?? 0 }));
}

/** Volume-weighted mid. An estimate: the feed carries a 10 s volume window, not trade prints. */
export function estimatedVwap(tape: TapeSample[]): number | null {
  let notional = 0;
  let volume = 0;
  for (const sample of tape) {
    notional += sample.price * sample.volume;
    volume += sample.volume;
  }
  return volume > 0 ? notional / volume : null;
}

export function tapeMedians(tape: TapeSample[]) {
  return {
    spreadBps: median(tape.map((sample) => sample.spreadBps ?? NaN)),
    bidDepth: median(tape.map((sample) => sample.bidDepth)),
    askDepth: median(tape.map((sample) => sample.askDepth)),
  };
}

/** Time ranges (sim seconds) where the stress detector sat at warning or worse. */
export function warningWindows(tape: TapeSample[]): Array<[number, number]> {
  const windows: Array<[number, number]> = [];
  let start: number | null = null;
  for (const sample of tape) {
    const raised = sample.level === 'warning' || sample.level === 'critical';
    if (raised && start === null) start = sample.t;
    if (!raised && start !== null) {
      windows.push([start, sample.t]);
      start = null;
    }
  }
  if (start !== null && tape.length) windows.push([start, tape.at(-1)!.t]);
  return windows;
}

/** The trailing 10 s aggressor window, sampled at the end of each bucket. */
export function flowBuckets(tape: TapeSample[], bucketSeconds = 5, count = 24) {
  const buckets = new Map<number, TapeSample>();
  for (const sample of tape) buckets.set(Math.floor(sample.t / bucketSeconds), sample);
  return [...buckets.values()].slice(-count).map((sample) => ({ t: sample.t, buy: sample.buy10, sell: sample.sell10 }));
}
