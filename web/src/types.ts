export interface Vehicle {
  id: string;
  type: string;
  x: number;
  y: number;
  z: number;
  angle_deg: number;
  speed_mps: number;
  length_m: number;
  width_m?: number;
}
export interface Signal {
  id: string;
  state: string;
}
export interface Frame {
  t: number;
  vehicles: Vehicle[];
  signals: Signal[];
  queue_count: number;
}
export interface World {
  world_id: "afterlight" | "baseline";
  policy: string;
  lead_s?: number | null;
  status: string;
  metrics: Record<string, unknown>;
  decision?: Record<string, unknown>;
  events: Array<Record<string, unknown>>;
  frames: Frame[];
}
export interface Replay {
  schema: "afterlight.replay.v1";
  mode: "recorded";
  scenario: {
    network_kind: "fixture" | "city";
    regime?: string;
    episode_id?: string;
    split?: string;
    id: string;
    seed: number;
    pickup_id: string;
    hospital_id: string;
    dispatch_s: number;
    route_edges?: string[];
  };
  coordinates: {
    source: string;
    position_reference: "front_bumper";
    render: string;
  };
  provenance: {
    [key: string]: unknown;
    source_commit: string;
    network_sha256: string;
    demand_sha256: string;
    sumo_version: string;
  };
  network_geometry?: { signals: SignalGeometry[] };
  selection_evidence?: SelectionEvidence | null;
  duration_s: number;
  step_s: number;
  worlds: { afterlight: World; baseline: World };
}
export interface CatalogEntry {
  policy_label?: string;
  sha256?: string;
  bytes?: number;
  id: string;
  title: string;
  url: string;
  pickup_id: string;
  hospital_id: string;
  seed: number;
  policy: string;
  lead_s?: number | null;
  duration_s: number;
}
export interface SignalLink {
  index: number;
  from_edge: string;
  to_edge: string;
  from_lane: string;
  to_lane: string;
  incoming_shape: number[][];
  outgoing_shape: number[][];
  stop_line: number[];
  turn: string;
  via_lane: string | null;
}
export interface SignalGeometry {
  id: string;
  position: number[];
  links: SignalLink[];
}
export interface City {
  schema: "afterlight.city.v1";
  edges: Array<{ id: string; centerline: number[][] }>;
  nodes: Array<{ id: string; position: number[]; signalized: boolean }>;
  roads: Array<{ id: string; centerline: number[][]; width_m: number }>;
  pickups: Array<{
    id: string;
    position: number[];
    edge_id: string;
    road_id: string;
  }>;
  hospitals: Array<{
    id: string;
    name?: string;
    driveway_anchor: number[];
    destination_node: string;
  }>;
  bounds: { min: number[]; max: number[] };
}

export interface SelectionEvidence {
  schema: "afterlight.selection-evidence.v1";
  selector_kind: "residual_tree" | "analytical";
  selector_sha256: string;
  model_sha256?: string | null;
  model_file_sha256?: string | null;
  study_sha256: string;
  protocol_sha256: string;
  release_sha256: string;
  report_sha256: string;
  selection_sha256: string;
  trace_manifest_sha256: string;
  collection_manifest_sha256: string;
  comparison_artifact_sha256: string;
  case_id: string;
  episode_id: string;
  selected_lead_s: number;
  source_world_aliases: Record<"baseline" | "afterlight", {
    original_world_id: string; trace_sha256: string; trace_file: string;
  }>;
  interpretation: string;
}
