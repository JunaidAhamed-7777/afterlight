import type { Replay } from "../../src/types.ts";
/** Empty structural unit fixture. Never simulation evidence or a publishable traffic result. */
export function structuralReplay(): Replay {
  const world = (name: "afterlight" | "baseline") => ({
    world_id: name, policy: name === "afterlight" ? "fixed" : "ordinary", status: "completed",
    metrics: {}, events: [], frames: [0, 1].map(t => ({ t, vehicles: [], signals: [], queue_count: 0 })),
  });
  return {
    schema: "afterlight.replay.v1", mode: "recorded",
    scenario: { id: "structural-unit-only", seed: 1, pickup_id: "fixture_start", hospital_id: "fixture_end", dispatch_s: 0, network_kind: "fixture" },
    coordinates: { source: "canonical XY meters", position_reference: "front_bumper", render: "[x,z,-y]" },
    provenance: { source_commit: "unit-fixture-no-simulator", network_sha256: "a".repeat(64), demand_sha256: "b".repeat(64), sumo_version: "no-simulator-executed" },
    duration_s: 1, step_s: 1, worlds: { afterlight: world("afterlight"), baseline: world("baseline") },
  };
}
