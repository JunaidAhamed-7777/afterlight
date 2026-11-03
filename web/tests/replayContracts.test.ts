import test from "node:test";
import assert from "node:assert/strict";
import { validateReplay } from "../src/replay.ts";
import { structuralReplay } from "./fixtures/structuralReplay.ts";
function signalRecording() {
  const replay = structuralReplay();
  const link = { index: 1, from_edge: "a", to_edge: "b", from_lane: "a_0", to_lane: "b_0", incoming_shape: [[0,0],[1,0]],
    outgoing_shape: [[2,0],[3,0]], stop_line: [1,0], turn: "s", via_lane: null };
  replay.network_geometry = { signals: [{ id: "J1", position: [1,0,0], links: [link, { ...link, to_edge: "c", to_lane: "c_0" }] }] };
  for (const world of Object.values(replay.worlds)) for (const frame of world.frames)
    frame.signals = [{ id: "J1", state: "Gr" }];
  return replay;
}
test("metrics require an object, not truthy arrays or primitive values", () => {
  for (const value of [[], "metrics", true, 1, null]) {
    const replay = structuralReplay(); replay.worlds.afterlight.metrics = value as unknown as Record<string, unknown>;
    assert.throws(() => validateReplay(replay));
  }
  assert.doesNotThrow(() => validateReplay(structuralReplay()));
});
test("shared controlled-link indexes are valid and geometry binds both world inventories", () => {
  assert.doesNotThrow(() => validateReplay(signalRecording()));
  for (const mutation of ["unknown", "missing", "short", "unstable"] as const) {
    const replay = signalRecording(); const frame = replay.worlds.baseline.frames[1];
    if (mutation === "unknown") frame.signals[0].id = "other";
    if (mutation === "missing") frame.signals = [];
    if (mutation === "short") frame.signals[0].state = "r";
    if (mutation === "unstable") frame.signals[0].state = "Grr";
    assert.throws(() => validateReplay(replay), /signal|Signal/);
  }
});
test("missing geometry keeps text-only signals valid; supplied empty geometry does not", () => {
  const replay = signalRecording(); delete replay.network_geometry;
  assert.doesNotThrow(() => validateReplay(replay));
  replay.network_geometry = { signals: [] };
  assert.throws(() => validateReplay(replay), /inventory/);
  const empty = structuralReplay(); empty.network_geometry = { signals: [] };
  assert.doesNotThrow(() => validateReplay(empty));
});
test("optional decisions remain optional and future planned requests are not clamped", () => {
  const replay = structuralReplay();
  assert.doesNotThrow(() => validateReplay(replay));
  replay.worlds.afterlight.decision = { t: 0, request_plan: { J1: 20 } };
  assert.doesNotThrow(() => validateReplay(replay));
  replay.worlds.afterlight.decision.request_plan = [];
  assert.throws(() => validateReplay(replay), /request plan/);
  replay.worlds.afterlight.decision = { t: 2 };
  assert.throws(() => validateReplay(replay), /decision time/);
});

test("required string identities reject objects and numbers before React rendering", () => {
  for (const key of ["id", "pickup_id", "hospital_id"] as const) {
    for (const value of [{ malformed: true }, 7, ""]) {
      const replay = structuralReplay();
      (replay.scenario as unknown as Record<string, unknown>)[key] = value;
      assert.throws(() => validateReplay(replay), /scenario or provenance/);
    }
  }
  for (const key of ["source_commit", "sumo_version"] as const) {
    const replay = structuralReplay(); replay.provenance[key] = {} as unknown as string;
    assert.throws(() => validateReplay(replay), /scenario or provenance/);
  }
  const policy = structuralReplay(); policy.worlds.afterlight.policy = 7 as unknown as string;
  assert.throws(() => validateReplay(policy));
  const link = signalRecording(); link.network_geometry!.signals[0].links[0].from_edge = {} as unknown as string;
  assert.throws(() => validateReplay(link), /controlled-link geometry/);
});


test("optional metrics status must match its physical world status", () => {
  assert.doesNotThrow(() => validateReplay(structuralReplay()));
  for (const name of ["afterlight", "baseline"] as const) {
    const matching = structuralReplay();
    matching.worlds[name].metrics.status = matching.worlds[name].status;
    assert.doesNotThrow(() => validateReplay(matching));
    for (const status of ["invalid", "censored", "infrastructure_error", null, true, {}]) {
      const replay = structuralReplay();
      replay.worlds[name].status = "completed";
      replay.worlds[name].metrics.status = status;
      assert.throws(() => validateReplay(replay), /metrics status does not match/);
    }
  }
});
