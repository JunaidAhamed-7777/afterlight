import type { Replay } from "./types.ts";
export const plainObject = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

/** Optional v1 geometry binds the actual signal inventory, including shared link indexes. */
export function validateSignalInventory(replay: Replay): void {
  const geometry = replay.network_geometry;
  if (geometry === undefined) return;
  const indexById = new Map(geometry.signals.map(signal => [signal.id, signal.links.reduce((max, link) => Math.max(max, link.index), -1)]));
  const lengths = new Map<string, number>();
  for (const world of [replay.worlds.afterlight, replay.worlds.baseline]) {
    for (const frame of world.frames) {
      if (frame.signals.length !== indexById.size || frame.signals.some(signal => !indexById.has(signal.id)))
        throw new Error("Frame signal inventory differs from recorded network geometry.");
      for (const signal of frame.signals) {
        if (indexById.get(signal.id)! >= signal.state.length)
          throw new Error("Signal state does not cover its controlled-link indexes.");
        if (lengths.has(signal.id) && lengths.get(signal.id) !== signal.state.length)
          throw new Error("Signal state length changes across the paired recording.");
        lengths.set(signal.id, signal.state.length);
      }
    }
  }
}
export function validateOptionalDecision(value: unknown, duration: number): void {
  if (!plainObject(value)) throw new Error("A supplied dispatch decision must be an object.");
  if (value.t !== undefined && (typeof value.t !== "number" || !Number.isFinite(value.t) || value.t < 0 || value.t > duration))
    throw new Error("Dispatch decision time is outside the recording.");
  if (value.request_plan !== undefined) {
    if (!plainObject(value.request_plan)) throw new Error("A supplied request plan must be an object.");
    for (const [junction, time] of Object.entries(value.request_plan))
      if (!junction || typeof time !== "number" || !Number.isFinite(time) || time < 0)
        throw new Error("A planned signal request has an invalid identity or time.");
    // Planned requests beyond duration remain valid for censored recordings.
  }
}
