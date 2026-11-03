import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { algorithmEvidence, ROUTING_SOURCE_HASHES, VIEWER_REFERENCE_COMMIT } from "../src/algorithm.ts";
import type { Replay, World } from "../src/types.ts";

// Synthetic metadata contracts only, never positive simulator evidence.
function fixture(): Replay {
  const world = (world_id: "afterlight" | "baseline"): World => ({
    world_id, policy: world_id === "baseline" ? "ordinary" : "fixed", lead_s: world_id === "baseline" ? 0 : 20, status: "completed",
    metrics: { ambulance_journey_s: world_id === "baseline" ? 12 : 10 },
    decision: { observation: { values: { route_distance_m: 123.4 } } },
    events: [], frames: [0, .5].map(t => ({ t, queue_count: 0, signals: [],
      vehicles: [{ id: "ambulance", type: "ambulance", x: 0, y: 0, z: 0,
        angle_deg: 90, speed_mps: 0, length_m: 4 }] })),
  });
  return {
    schema: "afterlight.replay.v1", mode: "recorded", duration_s: .5, step_s: .5,
    scenario: { id: "synthetic-metadata-only", network_kind: "city", seed: 1,
      pickup_id: "P_TEST", hospital_id: "H_TEST", dispatch_s: 0,
      route_edges: ["edge_B", "edge_A", "edge_B"] },
    coordinates: { source: "canonical XY meters", position_reference: "front_bumper", render: "[x,z,-y]" },
    provenance: { source_commit: "fa39f8a49c3ac2fcffe25ebf8c86e19dd6040fa3", source_dirty: false,
      source_files: { ...ROUTING_SOURCE_HASHES }, network_sha256: "a".repeat(64),
      demand_sha256: "b".repeat(64), sumo_version: "SYNTHETIC UNIT TEST" },
    worlds: { afterlight: world("afterlight"), baseline: world("baseline") },
  };
}

test("null recording has no fabricated route or algorithm evidence", () => {
  assert.equal(algorithmEvidence(null), null);
});

test("identified saved routing preserves exact edge order and keeps outcome/reference separate", () => {
  const replay = fixture(); const before = structuredClone(replay);
  const evidence = algorithmEvidence(replay)!;
  assert.equal(evidence.identifiedImplementation, true);
  assert.equal(evidence.sharedRoute, true);
  assert.deepEqual(evidence.routeEdges, ["edge_B", "edge_A", "edge_B"]);
  assert.notEqual(evidence.routeEdges, replay.scenario.route_edges);
  assert.equal(evidence.worlds[0].journeyS, 10);
  assert.equal(evidence.worlds[0].policy, "fixed");
  assert.equal(evidence.worlds[0].leadS, 20);
  assert.equal(evidence.worlds[0].laneDistanceM, 123.4);
  assert.equal(evidence.worlds[1].journeyS, 12);
  assert.equal(evidence.worlds[1].policy, "ordinary");
  assert.equal(evidence.worlds[1].leadS, null);
  assert.equal(evidence.worlds[1].hasRecordedAmbulance, true);
  assert.deepEqual(replay, before);
  assert.equal("searchCostM" in evidence, false, "No unexported numeric Dijkstra total is invented");
});

test("fixture identity stays distinct from city even with the same reviewed Dijkstra source", () => {
  const replay = fixture(); replay.scenario.network_kind = "fixture";
  const evidence = algorithmEvidence(replay)!;
  assert.equal(evidence.networkLabel, "Three-junction fixture");
  assert.equal(evidence.identifiedImplementation, true);
});

test("dirty, foreign and missing source fingerprints never inherit a Dijkstra/shared-route claim", () => {
  const changes = [
    (r: Replay) => { r.provenance.source_dirty = true; },
    (r: Replay) => { delete r.provenance.source_dirty; },
    (r: Replay) => { r.provenance.source_files = null; },
    ...Object.keys(ROUTING_SOURCE_HASHES).map(file => (r: Replay) => {
      (r.provenance.source_files as Record<string, string>)[file] = "f".repeat(64);
    }),
  ];
  for (const change of changes) {
    const replay = fixture(); change(replay);
    const evidence = algorithmEvidence(replay)!;
    assert.equal(evidence.identifiedImplementation, false);
    assert.equal(evidence.sharedRoute, false);
    assert.equal(evidence.worlds[0].laneDistanceM, null);
    assert.deepEqual(evidence.routeEdges, replay.scenario.route_edges);
    assert.deepEqual(evidence.captureSources.map(item => item.label),
      ["Reported network source", "Reported demand source", "Reported runner source"]);
  }
});

test("source links allow only full immutable commit IDs and fixed repository source paths", () => {
  for (const invalid of ["main", "a".repeat(41), "javascript:alert(1)", "../main", "a".repeat(40) + "?token=bad"]) {
    const replay = fixture(); replay.provenance.source_commit = invalid;
    const evidence = algorithmEvidence(replay)!;
    assert.equal(evidence.captureCommit, null);
    assert.deepEqual(evidence.captureSources, []);
    assert.equal(evidence.identifiedImplementation, false);
  }
  const evidence = algorithmEvidence(fixture())!;
  assert.equal(evidence.captureSources.length, 3);
  for (const item of evidence.captureSources)
    assert.match(item.href, /^https:\/\/github\.com\/JunaidAhamed-7777\/afterlight\/blob\/[a-f0-9]{40}\/sim\/[a-z]+\.py#L\d+$/);
  for (const item of evidence.viewerSources) assert.ok(item.href.includes(`/blob/${VIEWER_REFERENCE_COMMIT}/web/src/`));
});

test("missing route, missing poses and arbitrary cadence remain missing or explicitly recorded", () => {
  const replay = fixture(); delete replay.scenario.route_edges;
  replay.worlds.baseline.frames.forEach(frame => { frame.vehicles = []; });
  replay.step_s = 5;
  const evidence = algorithmEvidence(replay)!;
  assert.deepEqual(evidence.routeEdges, []);
  assert.equal(evidence.sharedRoute, false);
  assert.equal(evidence.worlds[1].hasRecordedAmbulance, false);
  assert.equal(evidence.sampleStepS, 5);
  replay.step_s = 0;
  assert.equal(algorithmEvidence(replay)!.sampleStepS, null);
});

test("unavailable or invalid metrics never become zero, and different references are not merged", () => {
  for (const invalid of [null, undefined, "12", false, -1, Infinity, NaN]) {
    const replay = fixture(); replay.worlds.afterlight.metrics.ambulance_journey_s = invalid;
    replay.worlds.afterlight.decision = { observation: { values: { route_distance_m: invalid } } };
    const evidence = algorithmEvidence(replay)!;
    assert.equal(evidence.worlds[0].journeyS, null);
    assert.equal(evidence.worlds[0].laneDistanceM, null);
  }
  const replay = fixture(); replay.worlds.afterlight.metrics.ambulance_journey_s = 0;
  replay.worlds.afterlight.decision = { observation: { values: { route_distance_m: 120 } } };
  const evidence = algorithmEvidence(replay)!;
  assert.equal(evidence.worlds[0].journeyS, 0);
  assert.equal(evidence.worlds[0].laneDistanceM, 120);
  assert.equal(evidence.worlds[1].laneDistanceM, 123.4);
});

test("actual released compact metadata supplies the two recorded lane references and shared source", () => {
  const saved = JSON.parse(fs.readFileSync(new URL("../../docs/validation/expanded-city-recordings.json", import.meta.url), "utf8"));
  const distances = [2824.8, 1742];
  saved.recordings.forEach((recording: { catalog: { evidence_url: string }; scenario: Replay["scenario"] }, index: number) => {
    const compact = JSON.parse(fs.readFileSync(new URL(`../public/replays/${recording.catalog.evidence_url}`, import.meta.url), "utf8"));
    const replay = fixture(); replay.scenario = recording.scenario; replay.provenance = compact.provenance;
    for (const row of compact.outcomes) {
      const world = replay.worlds[row.world_id as "afterlight" | "baseline"];
      world.metrics = row; world.decision = row.decision; world.status = row.status;
    }
    // Only extraction is tested; synthetic frame stubs are not measured poses.
    const evidence = algorithmEvidence(replay)!;
    assert.equal(evidence.identifiedImplementation, true);
    assert.equal(evidence.sharedRoute, true);
    assert.deepEqual(evidence.routeEdges, recording.scenario.route_edges);
    for (const world of evidence.worlds) assert.ok(Math.abs(world.laneDistanceM! - distances[index]) < 1e-8);
  });
});
