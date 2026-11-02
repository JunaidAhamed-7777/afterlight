import type { City, Frame } from "./types.ts";
const record = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);
const point = (value: unknown): value is number[] =>
  Array.isArray(value) && value.length >= 2 && value.every(Number.isFinite);
const nonempty = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0;
export function validateWorldIdentity(value: unknown): void {
  if (
    !record(value) ||
    Object.keys(value).sort().join(",") !== "afterlight,baseline"
  )
    throw new Error("Exactly two independent traffic worlds are required.");
  for (const key of ["afterlight", "baseline"])
    if (!record(value[key]) || value[key].world_id !== key)
      throw new Error("Recorded world identity does not match its source.");
  if ((value.baseline as Record<string, unknown>).policy !== "ordinary")
    throw new Error(
      "The counterfactual baseline must use ordinary signal control.",
    );
}
export function validateCadence(
  frames: Frame[],
  cadence: number,
  duration: number,
): void {
  for (let i = 1; i < frames.length; i++) {
    const delta = frames[i].t - frames[i - 1].t;
    const regular =
      Math.abs(delta - cadence) <= Math.max(1e-8, 1e-9 * Math.abs(cadence));
    const shortFinal = frames[i].t === duration && delta > 0 && delta < cadence;
    if (!regular && !shortFinal)
      throw new Error("The recording contains an undeclared sampling gap.");
  }
}
export function validatePhysicalIdentity(id: unknown, type: unknown): void {
  if (
    typeof id !== "string" ||
    !id ||
    id.toLowerCase().includes("ghost") ||
    (id === "ambulance") !== (type === "ambulance")
  )
    throw new Error(
      "The recording contains an invalid vehicle pose: ghost or noncanonical physical ambulance identity.",
    );
}
export function validateEvents(value: unknown, duration: number): void {
  if (!Array.isArray(value))
    throw new Error("Recorded lifecycle events must be a list.");
  for (const event of value) {
    if (
      !record(event) ||
      !nonempty(event.kind) ||
      typeof event.t !== "number" ||
      !Number.isFinite(event.t) ||
      event.t < 0 ||
      event.t > duration
    )
      throw new Error("A recorded event has an invalid timestamp or kind.");
    if (
      event.request_at_s !== undefined &&
      (typeof event.request_at_s !== "number" ||
        !Number.isFinite(event.request_at_s) ||
        event.request_at_s < event.t)
    )
      throw new Error("A planned priority request has invalid timing.");
  }
}
export function validateCity(value: unknown): City {
  if (
    !record(value) ||
    value.schema !== "afterlight.city.v1" ||
    !record(value.bounds) ||
    !point(value.bounds.min) ||
    !point(value.bounds.max)
  )
    throw new Error(
      "The canonical city map has an unsupported coordinate contract.",
    );
  const collections = [
    "nodes",
    "edges",
    "roads",
    "pickups",
    "hospitals",
  ] as const;
  const ids = new Map<string, Set<string>>();
  for (const name of collections) {
    const rows = value[name];
    if (!Array.isArray(rows)) throw new Error(`City ${name} must be a list.`);
    const seen = new Set<string>();
    for (const row of rows) {
      if (!record(row) || !nonempty(row.id) || seen.has(row.id))
        throw new Error(
          `City ${name} contains a missing or duplicate identity.`,
        );
      seen.add(row.id);
    }
    ids.set(name, seen);
  }
  for (const row of value.nodes as Array<Record<string, unknown>>)
    if (!point(row.position) || typeof row.signalized !== "boolean")
      throw new Error(
        "A city junction has an invalid position or signal flag.",
      );
  for (const name of ["edges", "roads"])
    for (const row of value[name] as Array<Record<string, unknown>>)
      if (
        !Array.isArray(row.centerline) ||
        row.centerline.length < 2 ||
        !row.centerline.every(point)
      )
        throw new Error("A canonical road has invalid geometry.");
  for (const row of value.pickups as Array<Record<string, unknown>>)
    if (
      !point(row.position) ||
      !ids.get("edges")!.has(String(row.edge_id)) ||
      !ids.get("roads")!.has(String(row.road_id))
    )
      throw new Error(
        "A pickup does not reference a valid canonical curb and edge.",
      );
  for (const row of value.hospitals as Array<Record<string, unknown>>)
    if (
      !point(row.driveway_anchor) ||
      !ids.get("nodes")!.has(String(row.destination_node)) ||
      (row.name !== undefined && typeof row.name !== "string")
    )
      throw new Error("A hospital has an invalid canonical destination.");
  return value as unknown as City;
}
