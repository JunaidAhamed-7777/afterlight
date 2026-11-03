import test from "node:test";
import assert from "node:assert/strict";
import { buildSignalTimeline, recordedSignalsAt } from "../src/signalTimeline.ts";
import type { World } from "../src/types.ts";

const world = (): World => ({ world_id: "afterlight", policy: "fixed", status: "completed", metrics: {},
  events: [
    { t: 0, junction: "J", kind: "green", phase: 0 },
    { t: 9, junction: "J", kind: "yellow", phase: 0 },
    { t: 12, junction: "J", kind: "all_red" },
    { t: 13, junction: "J", kind: "green", phase: 1 },
  ],
  frames: [0, 2, 4, 6, 8, 10, 12, 14, 16].map(t => ({ t, vehicles: [], queue_count: 0,
    signals: [{ id: "J", state: t < 9 ? "GGrr" : t < 12 ? "yyrr" : t < 13 ? "rrrr" : "rrGG" }] })),
});

test("lamps change at exact recorded boundaries between vehicle samples", () => {
  const w = world();
  assert.equal(buildSignalTimeline(w).size, 1);
  assert.equal(recordedSignalsAt(w, 8.99, w.frames[4].signals)[0].state, "GGrr");
  assert.equal(recordedSignalsAt(w, 9, w.frames[4].signals)[0].state, "yyrr");
  assert.equal(recordedSignalsAt(w, 12.5, w.frames[6].signals)[0].state, "rrrr");
  assert.equal(recordedSignalsAt(w, 13, w.frames[6].signals)[0].state, "rrGG");
  assert.equal(recordedSignalsAt(w, 4, w.frames[2].signals)[0].state, "GGrr");
});

test("contradictory or missing evidence retains sampled state", () => {
  const w = world();
  w.frames[2].signals[0].state = "rrGG";
  assert.equal(buildSignalTimeline(w).size, 0);
  assert.deepEqual(recordedSignalsAt(w, 9, w.frames[4].signals), w.frames[4].signals);
  const legacy = world(); legacy.events = [];
  assert.equal(buildSignalTimeline(legacy).size, 0);
});
