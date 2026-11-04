import type { QueuePoint, QueueSeries, QueueWorld } from "./queueTypes.ts";

export function queueCutoff(time: number, duration: number): number {
  return Number.isFinite(time) ? Math.max(0, Math.min(duration, time)) : 0;
}

/** Retain every actual sample through the cutoff; never interpolate a future one. */
export function revealedQueue(points: readonly QueuePoint[], cutoff: number): readonly QueuePoint[] {
  let low = 0, high = points.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (points[middle].t <= cutoff) low = middle + 1;
    else high = middle;
  }
  return points.slice(0, low);
}

/** Shared, integer-only axes. Recording axes use its complete known scale. */
export function queueScale(series: QueueSeries): { maximum: number; ticks: number[] } {
  let peak = 0;
  for (const world of ["afterlight", "baseline"] as const)
    for (const point of series[world]) peak = Math.max(peak, point.queue_count);
  const raw = Math.max(1, peak / 4);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = Math.max(1, [1, 2, 2.5, 5, 10].find((value) => value * magnitude >= raw)! * magnitude);
  const integerStep = Math.ceil(step);
  const maximum = Math.max(4 * integerStep, Math.ceil(peak / integerStep) * integerStep);
  return { maximum, ticks: Array.from({ length: maximum / integerStep + 1 }, (_, index) => index * integerStep) };
}

export function liveQueueWorld(series: QueueSeries): QueueWorld {
  return series.afterlight.length ? "afterlight" : "baseline";
}
