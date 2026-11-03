import type { Frame, Signal, World } from "./types.ts";

type Change = { t: number; state: string };
type Timeline = Map<string, Change[]>;
const memo = new WeakMap<World, Timeline>();
const stages = new Set(["green", "yellow", "all_red"]);

function stateAt(changes: Change[], t: number): string | undefined {
  let lo = 0, hi = changes.length - 1;
  if (hi < 0 || changes[0].t > t) return undefined;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (changes[mid].t <= t) lo = mid;
    else hi = mid - 1;
  }
  return changes[lo].state;
}

function firstFrameAtOrAfter(frames: Frame[], t: number): Frame | undefined {
  let lo = 0, hi = frames.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (frames[mid].t < t) lo = mid + 1;
    else hi = mid;
  }
  return frames[lo];
}

/** Recover exact recorded control boundaries without inventing vehicle poses.
 * Green strings come from genuine frames inside the corresponding legal green
 * interval. Yellow/all-red follow the audited conservative scheduler. A timeline
 * is accepted only when it reproduces every recorded lamp state for that signal.
 * Legacy or incomplete evidence keeps its original sampled presentation.
 */
export function buildSignalTimeline(world: World): Timeline {
  const initial = world.frames[0];
  const result: Timeline = new Map();
  if (!initial) return result;
  for (const signal of initial.signals) {
    const events = world.events.filter(event => event.junction === signal.id &&
      stages.has(String(event.kind)) && typeof event.t === "number" && Number.isFinite(event.t))
      .sort((a, b) => (a.t as number) - (b.t as number));
    if (!events.length) continue;
    const greens = new Map<number, string>();
    for (let i = 0; i < events.length; i++) {
      const event = events[i];
      if (event.kind !== "green" || typeof event.phase !== "number") continue;
      const frame = firstFrameAtOrAfter(world.frames, event.t as number);
      const until = events[i + 1]?.t as number | undefined;
      const measured = frame?.signals.find(value => value.id === signal.id)?.state;
      if (frame && measured && (until === undefined || frame.t < until) && /^[rRgG]+$/.test(measured)) {
        const previous = greens.get(event.phase);
        if (previous !== undefined && previous !== measured) {
          greens.clear();
          break;
        }
        greens.set(event.phase, measured);
      }
    }
    const changes: Change[] = [{ t: initial.t, state: signal.state }];
    let valid = true;
    for (const event of events) {
      const green = typeof event.phase === "number" ? greens.get(event.phase) : undefined;
      const state = event.kind === "all_red" ? "r".repeat(signal.state.length)
        : event.kind === "yellow" ? green?.replace(/[gG]/g, "y").replace(/[rR]/g, "r")
          : green;
      if (!state || state.length !== signal.state.length) { valid = false; break; }
      changes.push({ t: event.t as number, state });
    }
    if (valid && world.frames.every(frame => {
      const measured = frame.signals.find(value => value.id === signal.id)?.state;
      return measured === undefined || measured === stateAt(changes, frame.t);
    })) result.set(signal.id, changes);
  }
  return result;
}

export function recordedSignalsAt(world: World, t: number, sampled: Signal[]): Signal[] {
  let timeline = memo.get(world);
  if (!timeline) { timeline = buildSignalTimeline(world); memo.set(world, timeline); }
  return sampled.map(signal => ({ id: signal.id,
    state: stateAt(timeline.get(signal.id) ?? [], t) ?? signal.state }));
}
