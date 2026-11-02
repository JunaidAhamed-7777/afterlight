import {
  validateWorldIdentity,
  validateCadence,
  validatePhysicalIdentity,
  validateEvents,
} from "./validation.ts";
import type { Frame, Replay, Vehicle } from "./types.ts";
export function vehiclePose(v: Vehicle): [number, number, number, number] {
  const radians = (v.angle_deg * Math.PI) / 180;
  return [
    v.x - (Math.sin(radians) * v.length_m) / 2,
    v.z,
    -(v.y - (Math.cos(radians) * v.length_m) / 2),
    -radians,
  ];
}
export function frameAt(frames: Frame[], t: number): Frame | null {
  if (
    !Number.isFinite(t) ||
    !frames.length ||
    t < frames[0].t ||
    t > frames[frames.length - 1].t
  )
    return null;
  let low = 0,
    high = frames.length - 1;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (frames[mid].t <= t) low = mid;
    else high = mid - 1;
  }
  return frames[low];
}
export function validateReplay(value: unknown): Replay {
  const r = value as Replay;
  if (!r || r.schema !== "afterlight.replay.v1" || r.mode !== "recorded")
    throw new Error("This file is not a supported recorded AFTERLIGHT run.");
  if (
    !Number.isFinite(r.step_s) ||
    r.step_s <= 0 ||
    !Number.isFinite(r.duration_s) ||
    r.duration_s <= 0 ||
    !r.scenario ||
    !["fixture", "city"].includes(r.scenario.network_kind) ||
    !r.provenance ||
    r.coordinates?.position_reference !== "front_bumper" ||
    r.coordinates?.render !== "[x,z,-y]" ||
    r.coordinates?.source !== "canonical XY meters"
  )
    throw new Error(
      "The recording is missing its time, coordinate or provenance contract.",
    );
  if (
    !Number.isFinite(r.scenario.seed) ||
    !Number.isFinite(r.scenario.dispatch_s) ||
    r.scenario.dispatch_s < 0 ||
    !r.scenario.id ||
    !r.provenance.source_commit ||
    !r.provenance.sumo_version ||
    !/^[a-f0-9]{64}$/i.test(r.provenance.network_sha256) ||
    !/^[a-f0-9]{64}$/i.test(r.provenance.demand_sha256)
  )
    throw new Error(
      "The recording has incomplete scenario or provenance evidence.",
    );
  if (
    r.scenario.route_edges !== undefined &&
    (!Array.isArray(r.scenario.route_edges) ||
      r.scenario.route_edges.some((id) => typeof id !== "string" || !id))
  )
    throw new Error("The recording has invalid route references.");
  if (r.network_geometry !== undefined) {
    const point = (p: unknown): p is number[] =>
      Array.isArray(p) && p.length >= 2 && p.every(Number.isFinite);
    const ids = new Set<string>();
    if (!Array.isArray(r.network_geometry.signals))
      throw new Error("The recording has invalid signal geometry.");
    for (const signal of r.network_geometry.signals) {
      if (
        !signal.id ||
        ids.has(signal.id) ||
        !point(signal.position) ||
        !Array.isArray(signal.links)
      )
        throw new Error("The recording has invalid signal geometry.");
      ids.add(signal.id);
      for (const link of signal.links) {
        if (
          !Number.isInteger(link.index) ||
          link.index < 0 ||
          !link.from_edge ||
          !link.to_edge ||
          !link.from_lane ||
          !link.to_lane ||
          !point(link.stop_line) ||
          ![link.incoming_shape, link.outgoing_shape].every(
            (shape) =>
              Array.isArray(shape) && shape.length >= 2 && shape.every(point),
          )
        )
          throw new Error(
            "The recording has invalid controlled-link geometry.",
          );
      }
    }
  }
  validateWorldIdentity(r.worlds);
  for (const name of ["afterlight", "baseline"] as const) {
    const w = r.worlds?.[name];
    if (
      !w ||
      !["completed", "censored", "invalid", "infrastructure_error"].includes(
        w.status,
      ) ||
      !w.policy ||
      !w.metrics ||
      !Array.isArray(w.events) ||
      !Array.isArray(w.frames) ||
      !w.frames.length
    )
      throw new Error(`The ${name} world has no recorded frames.`);
    validateEvents(w.events, r.duration_s);
    let previous = -Infinity;
    for (const f of w.frames) {
      if (
        !Number.isFinite(f.t) ||
        f.t < 0 ||
        f.t > r.duration_s ||
        f.t <= previous ||
        !Number.isInteger(f.queue_count) ||
        f.queue_count < 0 ||
        !Array.isArray(f.vehicles) ||
        !Array.isArray(f.signals)
      )
        throw new Error(
          `The ${name} world has invalid or duplicate timestamps.`,
        );
      previous = f.t;
      const signalIds = new Set<string>();
      for (const signal of f.signals) {
        if (
          !signal.id ||
          signalIds.has(signal.id) ||
          typeof signal.state !== "string" ||
          !signal.state ||
          !/^[rRyYgGoOuUs]+$/.test(signal.state)
        )
          throw new Error(`The ${name} world has an invalid signal state.`);
        signalIds.add(signal.id);
      }
      const ids = new Set<string>();
      for (const v of f.vehicles) {
        validatePhysicalIdentity(v.id, v.type);
        if (
          !v.id ||
          (v.id === "ambulance") !== (v.type === "ambulance") ||
          ids.has(v.id) ||
          !["ambulance", "car", "truck", "bike"].includes(v.type) ||
          ![v.x, v.y, v.z, v.angle_deg, v.speed_mps, v.length_m].every(
            Number.isFinite,
          ) ||
          v.length_m <= 0 ||
          v.speed_mps < 0 ||
          (v.width_m !== undefined &&
            (!Number.isFinite(v.width_m) || v.width_m <= 0))
        )
          throw new Error(
            `The ${name} world contains an invalid vehicle pose.`,
          );
        ids.add(v.id);
      }
    }
    validateCadence(w.frames, r.step_s, r.duration_s);
    if (w.frames[0].t !== 0 || w.frames[w.frames.length - 1].t !== r.duration_s)
      throw new Error(
        `The ${name} world does not cover the declared playback horizon.`,
      );
  }
  const a = r.worlds.afterlight.frames,
    b = r.worlds.baseline.frames;
  if (a.length !== b.length || a.some((frame, index) => frame.t !== b[index].t))
    throw new Error(
      "The paired worlds do not cover the same absolute time interval.",
    );
  return r;
}
export const seconds = (value: unknown): string =>
  typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)} s`
    : "Not available";

/** Interpolate only display poses between adjacent real samples. Lifecycle and signals stay left-held. */
export function interpolatedFrame(frames: Frame[], t: number): Frame | null {
  const left = frameAt(frames, t);
  if (!left || left.t === t) return left;
  let low = 0,
    high = frames.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (frames[mid].t <= t) low = mid + 1;
    else high = mid;
  }
  const right = frames[low];
  if (!right || right.t <= left.t) return left;
  const alpha = (t - left.t) / (right.t - left.t);
  const next = new Map(right.vehicles.map((v) => [v.id, v]));
  const vehicles = left.vehicles.map((v) => {
    const n = next.get(v.id);
    if (!n || n.type !== v.type) return v;
    const distance = Math.hypot(n.x - v.x, n.y - v.y, n.z - v.z);
    // Teleports/discontinuities remain jumps, never fabricated traversals.
    if (
      distance >
      Math.max(v.speed_mps, n.speed_mps, 1) * (right.t - left.t) * 2 +
        v.length_m * 2 +
        5
    )
      return v;
    const turn = ((n.angle_deg - v.angle_deg + 540) % 360) - 180;
    return {
      ...v,
      x: v.x + (n.x - v.x) * alpha,
      y: v.y + (n.y - v.y) * alpha,
      z: v.z + (n.z - v.z) * alpha,
      angle_deg: v.angle_deg + turn * alpha,
    };
  });
  return { ...left, vehicles };
}
