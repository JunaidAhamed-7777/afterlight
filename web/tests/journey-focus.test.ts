import test from "node:test";
import assert from "node:assert/strict";
import type { City } from "../src/types.ts";
import { journeyAnchor, planJourneyFocus, MIN_JOURNEY_FOCUS_ZOOM, type JourneyFocus } from "../src/journeyFocus.ts";

// Synthetic CPU coordinate/camera fixtures only; no traffic or outcome evidence.
const city = {
  pickups: [{ id: "P001", position: [12, 25, 3] }],
  hospitals: [{ id: "HOSP_WEST", driveway_anchor: [-55, -10, 2], destination_node: "different-node" }],
  nodes: [{ id: "different-node", position: [900, 800, 0] }],
} as unknown as City;
const camera = { position: [100, 120, 150] as [number, number, number], target: [10, 20, 30] as [number, number, number], zoom: 2.5 };
const request: JourneyFocus = { kind: "pickup", id: "P001", revision: 1 };

test("selected anchors use canonical pickup and hospital driveway coordinates exactly once", () => {
  assert.deepEqual(journeyAnchor(city, "pickup", "P001"), [12, 3, -25]);
  assert.deepEqual(journeyAnchor(city, "hospital", "HOSP_WEST"), [-55, 2, 10]);
  const flat = { ...city, pickups: [{ id: "flat", position: [5, 8] }] } as unknown as City;
  assert.deepEqual(journeyAnchor(flat, "pickup", "flat"), [5, 0, -8]);
});

test("camera snap preserves its offset and existing close zoom without mutating source objects", () => {
  const before = JSON.stringify({ city, camera });
  const focused = planJourneyFocus(city, request, -1, camera)!;
  assert.deepEqual(focused.target, [12, 3, -25]);
  assert.deepEqual(focused.position, [102, 103, 95]);
  assert.equal(focused.zoom, MIN_JOURNEY_FOCUS_ZOOM);
  assert.equal(focused.revision, 1);
  assert.equal(planJourneyFocus(city, request, -1, { ...camera, zoom: 19 })!.zoom, 19);
  assert.equal(JSON.stringify({ city, camera }), before);
});

test("hospital focus uses its driveway rather than the routing destination node", () => {
  const focused = planJourneyFocus(city, { kind: "hospital", id: "HOSP_WEST", revision: 2 }, 1, camera)!;
  assert.deepEqual(focused.target, [-55, 2, 10]);
  assert.deepEqual(focused.position, [35, 102, 130]);
});

test("focus occurs only on a fresh explicit revision, including repeated selection of one ID", () => {
  assert.equal(planJourneyFocus(city, null, -1, camera), null);
  assert.equal(planJourneyFocus(city, request, 1, camera), null);
  assert.equal(planJourneyFocus(city, { ...request, revision: 0 }, 1, camera), null);
  assert.ok(planJourneyFocus(city, { ...request, revision: 2 }, 1, camera));
  assert.equal(planJourneyFocus(city, null, 1, camera), null);
  assert.equal(planJourneyFocus(city, request, 1, camera), null, "temporarily hiding a request must not reapply it");
});

test("missing city/IDs or malformed anchors never substitute a point or routing node", () => {
  assert.equal(planJourneyFocus(null, request, -1, camera), null);
  assert.equal(journeyAnchor(city, "pickup", "missing"), null);
  assert.equal(journeyAnchor(city, "hospital", "missing"), null);
  for (const point of [[], [1], [1, NaN], [1, 2, Infinity], new Array<number>(2), [1, 2, undefined]]) {
    const bad = { ...city, pickups: [{ id: "P001", position: point }] } as unknown as City;
    assert.equal(planJourneyFocus(bad, request, -1, camera), null);
  }
  const noDriveway = { ...city, hospitals: [{ id: "HOSP_WEST", destination_node: "different-node" }] } as unknown as City;
  assert.equal(journeyAnchor(noDriveway, "hospital", "HOSP_WEST"), null);
  assert.ok(planJourneyFocus(city, request, -1, camera), "an unavailable city need not consume the pending user request");
});

test("invalid revision and nonfinite camera state cannot move the view", () => {
  for (const revision of [-1, NaN, Infinity, 0.5, Number.MAX_SAFE_INTEGER + 1])
    assert.equal(planJourneyFocus(city, { ...request, revision }, -1, camera), null);
  for (const zoom of [0, -1, NaN, Infinity])
    assert.equal(planJourneyFocus(city, request, -1, { ...camera, zoom }), null);
  assert.equal(planJourneyFocus(city, request, -1, { ...camera, target: [0, NaN, 0] }), null);
  assert.equal(planJourneyFocus(city, request, -1, { ...camera, position: [Infinity, 0, 0] }), null);
});
