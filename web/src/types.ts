export interface Vehicle {
  id: string;
  type: string;
  x: number;
  y: number;
  z: number;
  angle_deg: number;
  speed_mps: number;
  length_m: number;
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
  policy: string;
  status: string;
  metrics: Record<string, unknown>;
  events: Array<Record<string, unknown>>;
  frames: Frame[];
}
export interface Replay {
  schema: "afterlight.replay.v1";
  mode: "recorded";
  scenario: {
    network_kind: "fixture" | "city";
    id: string;
    seed: number;
    pickup_id: string;
    hospital_id: string;
    dispatch_s: number;
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
  duration_s: number;
  step_s: number;
  worlds: { afterlight: World; baseline: World };
}
export interface CatalogEntry {
  id: string;
  title: string;
  url: string;
  pickup_id: string;
  hospital_id: string;
  seed: number;
  policy: string;
  duration_s: number;
}
export interface City {
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
