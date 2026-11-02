import test from "node:test";
import assert from "node:assert/strict";
import { frameAt, validateReplay, vehiclePose } from "../src/replay.ts";
import type { Replay, Vehicle, Frame } from "../src/types.ts";
const vehicle: Vehicle = {
  id: "ambulance",
  type: "ambulance",
  x: 100,
  y: 200,
  z: 0,
  angle_deg: 0,
  speed_mps: 10,
  length_m: 6,
};
const frame = (t: number): Frame => ({
  t,
  vehicles: [{ ...vehicle }],
  signals: [],
  queue_count: 0,
});
function recording(): Replay {
  return {
    schema: "afterlight.replay.v1",
    mode: "recorded",
    scenario: {
      id: "test-fixture-only",
      network_kind: "fixture",
      seed: 1,
      pickup_id: "fixture_start",
      hospital_id: "fixture_end",
      dispatch_s: 0,
    },
    coordinates: {
      source: "canonical XY meters",
      position_reference: "front_bumper",
      render: "[x,z,-y]",
    },
    provenance: {
      source_commit: "unit-fixture",
      network_sha256: "a".repeat(64),
      demand_sha256: "b".repeat(64),
      sumo_version: "not-a-simulation",
    },
    duration_s: 1,
    step_s: 1,
    worlds: {
      afterlight: {
        world_id: "afterlight",
        policy: "fixed",
        status: "completed",
        metrics: {},
        events: [],
        frames: [frame(0), frame(1)],
      },
      baseline: {
        world_id: "baseline",
        policy: "ordinary",
        status: "completed",
        metrics: {},
        events: [],
        frames: [frame(0), frame(1)],
      },
    },
  };
}
test("north heading converts front bumper to model center without changing absolute scale", () => {
  assert.deepEqual(vehiclePose(vehicle), [100, 0, -197, -0]);
});
test("east heading rotates model forward -Z to +X and offsets center", () => {
  const pose = vehiclePose({ ...vehicle, angle_deg: 90 });
  assert.equal(pose[0], 97);
  assert.equal(pose[2], -200);
  assert.equal(pose[3], -Math.PI / 2);
});
test("frame lookup uses one absolute clock and never extrapolates before beginning", () => {
  const frames = [frame(2), frame(4), frame(8)];
  assert.equal(frameAt(frames, 1), null);
  assert.equal(frameAt(frames, 5)?.t, 4);
  assert.equal(frameAt(frames, 8)?.t, 8);
  assert.equal(frameAt(frames, 9), null);
});
test("valid fixture may be inspected but remains explicitly fixture", () => {
  assert.equal(validateReplay(recording()).scenario.network_kind, "fixture");
});
test("unknown map provenance is rejected rather than overlaid on the city", () => {
  const r = recording();
  delete (r.scenario as Partial<Replay["scenario"]>).network_kind;
  assert.throws(() => validateReplay(r), /contract/);
});
test("duplicate vehicle IDs fail closed", () => {
  const r = recording();
  r.worlds.afterlight.frames[0].vehicles.push({ ...vehicle });
  assert.throws(() => validateReplay(r), /invalid vehicle pose/);
});
test("out-of-order samples fail closed", () => {
  const r = recording();
  r.worlds.afterlight.frames[1].t = 0;
  assert.throws(() => validateReplay(r), /timestamps/);
});
test("worlds must have identical sampled absolute timestamps", () => {
  const r = recording();
  r.step_s = 0.5;
  r.worlds.afterlight.frames.splice(1, 0, frame(0.5));
  r.worlds.baseline.frames.splice(1, 0, frame(0.5000000001));
  assert.throws(() => validateReplay(r), /absolute time/);
});
test("ghost pose is baseline data and does not mutate active world", () => {
  const r = recording();
  r.worlds.baseline.frames[0].vehicles[0].x = 70;
  const before = JSON.stringify(r.worlds.afterlight);
  assert.equal(
    vehiclePose(frameAt(r.worlds.baseline.frames, 0)!.vehicles[0])[0],
    70,
  );
  assert.equal(JSON.stringify(r.worlds.afterlight), before);
});
test("non-finite vehicle position rejected", () => {
  const r = recording();
  r.worlds.baseline.frames[0].vehicles[0].x = NaN;
  assert.throws(() => validateReplay(r), /invalid vehicle pose/);
});

test("pose interpolation keeps signal/count observations unchanged", async () => {
  const { interpolatedFrame } = await import("../src/replay.ts");
  const a = frame(0),
    b = frame(1);
  a.queue_count = 3;
  a.signals = [{ id: "J1", state: "rG" }];
  b.queue_count = 7;
  b.signals = [{ id: "J1", state: "Gr" }];
  b.vehicles[0].x = 110;
  const result = interpolatedFrame([a, b], 0.5)!;
  assert.equal(result.vehicles[0].x, 105);
  assert.equal(result.queue_count, 3);
  assert.deepEqual(result.signals, a.signals);
  assert.equal(a.vehicles[0].x, 100);
});
test("interpolation uses shortest heading across north", async () => {
  const { interpolatedFrame } = await import("../src/replay.ts");
  const a = frame(0),
    b = frame(1);
  a.vehicles[0].angle_deg = 359;
  b.vehicles[0].angle_deg = 1;
  assert.equal(interpolatedFrame([a, b], 0.5)!.vehicles[0].angle_deg, 360);
});
test("new and departed vehicles have no invented lifecycle", async () => {
  const { interpolatedFrame } = await import("../src/replay.ts");
  const a = frame(0),
    b = frame(1);
  b.vehicles = [{ ...vehicle, id: "new" }];
  const result = interpolatedFrame([a, b], 0.5)!;
  assert.deepEqual(
    result.vehicles.map((v) => v.id),
    ["ambulance"],
  );
  assert.deepEqual(
    interpolatedFrame([a, b], 1)!.vehicles.map((v) => v.id),
    ["new"],
  );
  assert.equal(interpolatedFrame([a, b], 2), null);
});
test("teleport discontinuities are not animated as road travel", async () => {
  const { interpolatedFrame } = await import("../src/replay.ts");
  const a = frame(0),
    b = frame(1);
  b.vehicles[0].x = 900;
  assert.equal(interpolatedFrame([a, b], 0.5)!.vehicles[0].x, 100);
});

test("malformed controlled-link geometry rejected before rendering", () => {
  const r = recording();
  r.network_geometry = {
    signals: [
      {
        id: "J1",
        position: [0, 0, 0],
        links: [
          {
            index: 0,
            from_edge: "a",
            to_edge: "b",
            from_lane: "a_0",
            to_lane: "b_0",
            incoming_shape: [
              [0, 0],
              [1, 0],
            ],
            outgoing_shape: [
              [2, 0],
              [NaN, 0],
            ],
            stop_line: [1, 0],
            turn: "s",
            via_lane: null,
          },
        ],
      },
    ],
  };
  assert.throws(() => validateReplay(r), /controlled-link geometry/);
});

test("declared duration cannot extend beyond actual trace coverage", () => {
  const r = recording();
  r.duration_s = 2;
  assert.throws(() => validateReplay(r), /playback horizon/);
});
test("a second physical ambulance identity is rejected", () => {
  const r = recording();
  r.worlds.afterlight.frames[0].vehicles.push({ ...vehicle, id: "ghost" });
  assert.throws(() => validateReplay(r), /vehicle pose/);
});

test("nonordinary counterfactual and swapped world identity fail before playback", () => {
  const a = recording();
  a.worlds.baseline.policy = "fixed";
  assert.throws(() => validateReplay(a), /ordinary/);
  const b = recording();
  b.worlds.baseline.world_id = "afterlight";
  assert.throws(() => validateReplay(b), /identity/);
});
test("physical civilian ghost IDs and undeclared sample gaps fail closed", () => {
  const a = recording();
  a.worlds.afterlight.frames[0].vehicles.push({
    ...vehicle,
    id: "ghost_car",
    type: "car",
  });
  assert.throws(() => validateReplay(a), /ghost/);
  const b = recording();
  b.step_s = 0.5;
  assert.throws(() => validateReplay(b), /sampling gap/);
});
