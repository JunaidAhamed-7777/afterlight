import type { City } from "./types.ts";

/** An explicit user selection. Revisions increase even when an ID is reselected. */
export interface JourneyFocus {
  kind: "pickup" | "hospital";
  id: string;
  revision: number;
}

export type JourneyPoint = [number, number, number];
export const MIN_JOURNEY_FOCUS_ZOOM = 8;

/** Render coordinates only: canonical XY/elevation become Three.js X/Y/-Z. */
export function journeyAnchor(
  city: City | null,
  kind: JourneyFocus["kind"],
  id: string,
): JourneyPoint | null {
  const point = kind === "pickup"
    ? city?.pickups.find((row) => row.id === id)?.position
    : kind === "hospital"
      ? city?.hospitals.find((row) => row.id === id)?.driveway_anchor
      : undefined;
  const elevation = point?.length === 2 ? 0 : point?.[2];
  if (!point || point.length < 2 || ![point[0], point[1], elevation].every(Number.isFinite))
    return null;
  return [point[0], elevation!, -point[1]];
}

/** One instant camera translation; it never changes view mode, roll or physics. */
export function planJourneyFocus(
  city: City | null,
  request: JourneyFocus | null,
  appliedRevision: number,
  camera: { position: JourneyPoint; target: JourneyPoint; zoom: number },
): { revision: number; position: JourneyPoint; target: JourneyPoint; zoom: number } | null {
  if (!request || !Number.isSafeInteger(request.revision) || request.revision < 0 ||
      request.revision <= appliedRevision) return null;
  const target = journeyAnchor(city, request.kind, request.id);
  if (!target || !camera.position.every(Number.isFinite) ||
      !camera.target.every(Number.isFinite) || !Number.isFinite(camera.zoom) || camera.zoom <= 0)
    return null;
  return {
    revision: request.revision,
    position: camera.position.map((value, axis) => value + target[axis] - camera.target[axis]) as JourneyPoint,
    target,
    zoom: Math.max(camera.zoom, MIN_JOURNEY_FOCUS_ZOOM),
  };
}
