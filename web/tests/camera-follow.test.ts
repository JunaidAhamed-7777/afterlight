import test from "node:test";
import assert from "node:assert/strict";
import { AmbulanceCameraTrack, cameraSeek, followBlend, MAX_CAMERA_ZOOM } from "../src/cameraFollow.ts";
import type { Frame, Vehicle } from "../src/types.ts";
const vehicle = (x: number): Vehicle => ({ id: "ambulance", type: "ambulance", x, y: 20, z: 2, angle_deg: 90, speed_mps: 10, length_m: 6 });
const frame = (t: number, v?: Vehicle): Frame => ({t, vehicles: v ? [v] : [], signals: [], queue_count: 0});
test("camera targets actual interpolated ambulance center, preserving source frames", () => {
  const frames = [frame(0), frame(10, vehicle(10)), frame(11, vehicle(20)), frame(12)];
  const original = JSON.stringify(frames), track = new AmbulanceCameraTrack(frames);
  assert.deepEqual(track.target(10.5), [12, 3.5, -20]);
  assert.equal(JSON.stringify(frames), original);
});
test("camera holds first/last actual pose before insertion and after arrival, including reverse seek", () => {
  const track = new AmbulanceCameraTrack([frame(0), frame(10, vehicle(10)), frame(11, vehicle(20)), frame(12)]);
  assert.deepEqual(track.target(0), track.target(10));
  assert.deepEqual(track.target(200), track.target(11));
  assert.deepEqual(track.target(0), [7, 3.5, -20]);
  assert.equal(new AmbulanceCameraTrack([frame(0)]).target(0), null);
  assert.equal(track.target(NaN), null);
});
test("camera holds missing observed interval rather than manufacturing a vehicle", () => {
  const track = new AmbulanceCameraTrack([frame(0, vehicle(10)), frame(1), frame(2, vehicle(30))]);
  assert.deepEqual(track.target(1.5), [7, 3.5, -20]);
});
test("playing follow blends smoothly and seek discontinuities are explicit", () => {
  assert.equal(cameraSeek(null, 50, .016), false);
  assert.equal(cameraSeek(20, 19, .016), true);
  assert.equal(cameraSeek(20, 80, .016), true);
  assert.equal(cameraSeek(20, 20.064, .016), false);
  assert.equal(cameraSeek(20, 20, .016), false);
  assert.ok(followBlend(.016) > 0 && followBlend(.016) < 1);
  assert.equal(followBlend(0), 0);
  assert.equal(followBlend(2), followBlend(.1));
  assert.ok(MAX_CAMERA_ZOOM > 12);
});

test("paused follow locks to the recorded target without residual settling", () => {
  for (const elapsed of [0, .001, .016, .1, 2]) {
    assert.equal(followBlend(elapsed, false), 1);
  }
  assert.equal(followBlend(.016, true), followBlend(.016));
});
