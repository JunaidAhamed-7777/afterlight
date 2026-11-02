import type { Frame, Replay, Vehicle } from './types.ts';
export function vehiclePose(v: Vehicle): [number, number, number, number] {
 const radians = v.angle_deg * Math.PI / 180;
 return [v.x - Math.sin(radians) * v.length_m / 2, v.z, -(v.y - Math.cos(radians) * v.length_m / 2), -radians];
}
export function frameAt(frames: Frame[], t: number): Frame | null {
 if (!frames.length || t < frames[0].t || t > frames[frames.length-1].t) return null;
 let low = 0, high = frames.length - 1;
 while (low < high) { const mid = Math.ceil((low + high) / 2); if (frames[mid].t <= t) low = mid; else high = mid - 1; }
 return frames[low];
}
export function validateReplay(value: unknown): Replay {
 const r = value as Replay;
 if (!r || r.schema !== 'afterlight.replay.v1' || r.mode !== 'recorded') throw new Error('This file is not a supported recorded AFTERLIGHT run.');
 if (!Number.isFinite(r.step_s) || r.step_s <= 0 || !Number.isFinite(r.duration_s) || r.duration_s <= 0 || !r.scenario || !['fixture','city'].includes(r.scenario.network_kind) || !r.provenance || r.coordinates?.position_reference !== 'front_bumper' || r.coordinates?.render !== '[x,z,-y]' || r.coordinates?.source !== 'canonical XY meters') throw new Error('The recording is missing its time, coordinate or provenance contract.');
 if (!Number.isFinite(r.scenario.seed) || !Number.isFinite(r.scenario.dispatch_s) || r.scenario.dispatch_s < 0 || !r.scenario.id || !r.provenance.source_commit || !r.provenance.sumo_version || !/^[a-f0-9]{64}$/i.test(r.provenance.network_sha256) || !/^[a-f0-9]{64}$/i.test(r.provenance.demand_sha256)) throw new Error('The recording has incomplete scenario or provenance evidence.');
 for (const name of ['afterlight', 'baseline'] as const) {
  const w = r.worlds?.[name];
  if (!w || !['completed','censored','invalid','infrastructure_error'].includes(w.status) || !w.policy || !w.metrics || !Array.isArray(w.events) || !Array.isArray(w.frames) || !w.frames.length) throw new Error(`The ${name} world has no recorded frames.`);
  let previous = -Infinity;
  for (const f of w.frames) {
   if (!Number.isFinite(f.t) || f.t < 0 || f.t > r.duration_s || f.t <= previous || !Number.isInteger(f.queue_count) || f.queue_count < 0 || !Array.isArray(f.vehicles) || !Array.isArray(f.signals)) throw new Error(`The ${name} world has invalid or duplicate timestamps.`);
   previous = f.t;
   const signalIds = new Set<string>();
   for (const signal of f.signals) { if (!signal.id || signalIds.has(signal.id) || typeof signal.state !== 'string' || !signal.state || !/^[rRyYgGoOuUs]+$/.test(signal.state)) throw new Error(`The ${name} world has an invalid signal state.`); signalIds.add(signal.id); }
   const ids = new Set<string>();
   for (const v of f.vehicles) { if (!v.id || ids.has(v.id) || !['ambulance','car','truck','bike'].includes(v.type) || ![v.x,v.y,v.z,v.angle_deg,v.speed_mps,v.length_m].every(Number.isFinite) || v.length_m <= 0 || v.speed_mps < 0) throw new Error(`The ${name} world contains an invalid vehicle pose.`); ids.add(v.id); }
  }
 }
 const a = r.worlds.afterlight.frames, b = r.worlds.baseline.frames;
 if (a.length !== b.length || a.some((frame,index) => frame.t !== b[index].t)) throw new Error('The paired worlds do not cover the same absolute time interval.');
 return r;
}
export const seconds = (value: unknown): string => typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)} s` : 'Not available';
