export interface PriceSample { receivedAt: number; price: number; fundamental?: number }
export interface Candle { time: number; open: number; high: number; low: number; close: number; fundamental?: number }

export function aggregateCandles(samples: PriceSample[], intervalMs: number): Candle[] {
  if (!Number.isFinite(intervalMs) || intervalMs <= 0) throw new RangeError('Invalid candle interval');
  const buckets = new Map<number, Candle>();
  const valid = samples.filter(p => Number.isFinite(p.receivedAt) && Number.isFinite(p.price))
    .sort((a, b) => a.receivedAt - b.receivedAt);
  for (const point of valid) {
    const time = Math.floor(point.receivedAt / intervalMs) * intervalMs;
    const candle = buckets.get(time);
    if (candle) {
      candle.high = Math.max(candle.high, point.price);
      candle.low = Math.min(candle.low, point.price);
      candle.close = point.price;
      candle.fundamental = point.fundamental;
    } else buckets.set(time, { time, open: point.price, high: point.price, low: point.price, close: point.price, fundamental: point.fundamental });
  }
  return [...buckets.values()];
}
