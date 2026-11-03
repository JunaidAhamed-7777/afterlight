import type { Replay, World } from "./types.ts";

/** Reviewed capture implementation, identified by exported whole-file digests. */
export const ROUTING_SOURCE_HASHES = {
  "sim/network.py": "9fc5578664b00ef4e5a307998133c605786378a2f794fbee4b5421a15e33b779",
  "sim/demand.py": "b9cb1c63db28b2ab4df243d4a07563147cd412d072a911be4f0921b5783bd925",
  "sim/run.py": "eccde802007afabd76106d8fc6b0466f8b697fbff233282af99601fd59ce6b45",
} as const;

// The referenced pose/overlay implementation is unchanged by this explanatory UI.
export const VIEWER_REFERENCE_COMMIT = "9fafa929e377203d3a4d33ca23065f608a736a52";
const REPOSITORY = "https://github.com/JunaidAhamed-7777/afterlight";
const COMMIT = /^(?:[a-f0-9]{40}|[a-f0-9]{64})$/;
const SHA256 = /^[a-f0-9]{64}$/;

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}

function nonnegative(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

export interface AlgorithmSource {
  label: string;
  file: string;
  href: string;
}

export interface AlgorithmWorld {
  id: "afterlight" | "baseline";
  policy: string;
  leadS: number | null;
  status: string;
  journeyS: number | null;
  laneDistanceM: number | null;
  hasRecordedAmbulance: boolean;
}

export interface AlgorithmEvidence {
  identifiedImplementation: boolean;
  sharedRoute: boolean;
  networkLabel: string;
  pickup: string;
  hospital: string;
  routeEdges: string[];
  sampleStepS: number | null;
  captureCommit: string | null;
  sourceDirty: boolean | null;
  sourceHashes: Array<{ file: string; sha256: string | null }>;
  captureSources: AlgorithmSource[];
  viewerSources: AlgorithmSource[];
  worlds: AlgorithmWorld[];
  offlineSelection: boolean;
}

function source(commit: string, file: string, line: number, label: string): AlgorithmSource {
  return { label, file, href: `${REPOSITORY}/blob/${commit}/${file}#L${line}` };
}

/** Read recorded metadata only. Never solve, infer from poses, sort or alter a route. */
export function algorithmEvidence(replay: Replay | null): AlgorithmEvidence | null {
  if (!replay) return null;
  const commit = COMMIT.test(replay.provenance.source_commit) ? replay.provenance.source_commit : null;
  const files = object(replay.provenance.source_files);
  const clean = replay.provenance.source_dirty === false;
  const identified = Boolean(commit && clean && Object.entries(ROUTING_SOURCE_HASHES)
    .every(([file, digest]) => files?.[file] === digest));
  const supplied = replay.scenario.route_edges;
  const edges = Array.isArray(supplied) && supplied.every(id => typeof id === "string" && id.length > 0)
    ? supplied.slice() : [];
  const world = (id: "afterlight" | "baseline", value: World): AlgorithmWorld => {
    const observation = object(object(value.decision)?.observation);
    const values = object(observation?.values);
    return { id, policy: value.policy,
      leadS: value.policy === "ordinary" ? null : nonnegative(value.lead_s),
      status: value.status, journeyS: nonnegative(value.metrics.ambulance_journey_s),
      laneDistanceM: identified ? nonnegative(values?.route_distance_m) : null,
      hasRecordedAmbulance: value.frames.some(frame => frame.vehicles.some(vehicle =>
        vehicle.id === "ambulance" && vehicle.type === "ambulance")) };
  };
  return {
    identifiedImplementation: identified,
    sharedRoute: identified && edges.length > 0,
    networkLabel: replay.scenario.network_kind === "city" ? "Expanded city" :
      replay.scenario.network_kind === "fixture" ? "Three-junction fixture" : "Recorded network",
    pickup: replay.scenario.pickup_id, hospital: replay.scenario.hospital_id,
    routeEdges: edges,
    sampleStepS: typeof replay.step_s === "number" && Number.isFinite(replay.step_s) && replay.step_s > 0
      ? replay.step_s : null,
    captureCommit: commit,
    sourceDirty: typeof replay.provenance.source_dirty === "boolean" ? replay.provenance.source_dirty : null,
    sourceHashes: Object.keys(ROUTING_SOURCE_HASHES).map(file => ({ file,
      sha256: typeof files?.[file] === "string" && SHA256.test(files[file] as string) ? files[file] as string : null })),
    captureSources: commit ? [
      source(commit, "sim/network.py", 74, identified ? "Dijkstra search and tie handling" : "Reported network source"),
      source(commit, "sim/demand.py", 108, identified ? "Pickup, destination and saved route" : "Reported demand source"),
      source(commit, "sim/run.py", 440, identified ? "Paired simulations and route export" : "Reported runner source"),
    ] : [],
    viewerSources: [
      source(VIEWER_REFERENCE_COMMIT, "web/src/replay.ts", 10, "Front-bumper to model coordinates"),
      source(VIEWER_REFERENCE_COMMIT, "web/src/replay.ts", 198, "Saved-pose interpolation"),
      source(VIEWER_REFERENCE_COMMIT, "web/src/GeometryLayer.ts", 24, "Road-center route overlay"),
      source(VIEWER_REFERENCE_COMMIT, "web/src/CityView.tsx", 703, "Ordinary-world ghost playback"),
    ],
    worlds: [world("afterlight", replay.worlds.afterlight), world("baseline", replay.worlds.baseline)],
    offlineSelection: Boolean(replay.selection_evidence),
  };
}
