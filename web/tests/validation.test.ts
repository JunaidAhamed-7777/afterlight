import test from "node:test";
import assert from "node:assert/strict";
import {
  validateWorldIdentity,
  validateCadence,
  validatePhysicalIdentity,
  validateEvents,
  validateCity,
} from "../src/validation.ts";
import type { Frame } from "../src/types.ts";
const frame = (t: number): Frame => ({
  t,
  vehicles: [],
  signals: [],
  queue_count: 0,
});
test("counterfactual must be ordinary in its own correctly identified world", () => {
  const worlds = {
    afterlight: { world_id: "afterlight", policy: "fixed" },
    baseline: { world_id: "baseline", policy: "ordinary" },
  };
  validateWorldIdentity(worlds);
  assert.throws(
    () =>
      validateWorldIdentity({
        ...worlds,
        baseline: { ...worlds.baseline, policy: "fixed" },
      }),
    /ordinary/,
  );
  assert.throws(
    () =>
      validateWorldIdentity({
        ...worlds,
        baseline: { ...worlds.baseline, world_id: "afterlight" },
      }),
    /identity/,
  );
  assert.throws(
    () => validateWorldIdentity({ ...worlds, extra: {} }),
    /Exactly two/,
  );
});
test("cadence permits only a declared regular interval or shorter common endpoint", () => {
  validateCadence([frame(0), frame(1), frame(1.5)], 1, 1.5);
  assert.throws(
    () => validateCadence([frame(0), frame(1), frame(3)], 1, 3),
    /sampling gap/,
  );
});
test("ghost IDs are rejected for every physical vehicle type", () => {
  assert.throws(
    () => validatePhysicalIdentity("baseline_GHOST_car", "car"),
    /ghost/,
  );
  assert.throws(
    () => validatePhysicalIdentity("second", "ambulance"),
    /ambulance/,
  );
  validatePhysicalIdentity("ambulance", "ambulance");
});
test("malformed event timing cannot reach the decision inspector", () => {
  validateEvents([{ t: 1, kind: "dispatch" }], 2);
  assert.throws(
    () => validateEvents([{ t: NaN, kind: "dispatch" }], 2),
    /timestamp/,
  );
  assert.throws(
    () => validateEvents([{ t: 3, kind: "dispatch" }], 2),
    /timestamp/,
  );
  assert.throws(
    () =>
      validateEvents([{ t: 1, kind: "request_planned", request_at_s: 0 }], 2),
    /timing/,
  );
});
test("nested city collections reject malformed anchors before App renders", () => {
  const city = {
    schema: "afterlight.city.v1",
    bounds: { min: [0, 0, 0], max: [10, 10, 1] },
    nodes: [{ id: "n", position: [0, 0, 0], signalized: false }],
    roads: [
      {
        id: "r",
        centerline: [
          [0, 0],
          [1, 0],
        ],
        width_m: 5,
      },
    ],
    edges: [
      {
        id: "e",
        centerline: [
          [0, 0],
          [1, 0],
        ],
      },
    ],
    pickups: [{ id: "p", position: [0, 1, 0], edge_id: "e", road_id: "r" }],
    hospitals: [
      {
        id: "h",
        name: "Test fixture",
        destination_node: "n",
        driveway_anchor: [0, 0, 0],
      },
    ],
  };
  validateCity(city);
  assert.throws(() => validateCity({ ...city, pickups: [null] }), /identity/);
  assert.throws(
    () =>
      validateCity({
        ...city,
        pickups: [{ ...city.pickups[0], position: [NaN, 0] }],
      }),
    /pickup/i,
  );
  assert.throws(
    () =>
      validateCity({
        ...city,
        hospitals: [{ ...city.hospitals[0], destination_node: "missing" }],
      }),
    /hospital/i,
  );
});
