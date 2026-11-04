import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { randomJourney } from "../src/journeySelection.ts";
import type { City } from "../src/types.ts";

// Small selection-domain fixtures, not traffic or route evidence.
function fixture(pickups = ["P001", "P002"], hospitals = ["HOSP_WEST", "HOSP_EAST"]): City {
  return {
    schema: "afterlight.city.v1", edges: [], nodes: [], roads: [],
    pickups: pickups.map(id => ({ id, position: [0, 0], edge_id: "edge", road_id: "road" })),
    hospitals: hospitals.map(id => ({ id, driveway_anchor: [0, 0], destination_node: "node" })),
    bounds: { min: [0, 0], max: [1, 1] },
  };
}
const key = (pair: { pickup: string; hospital: string }) => `${pair.pickup}/${pair.hospital}`;

test("all 200 canonical pairs are selectable, including both hospitals and every pickup", () => {
  const city = JSON.parse(fs.readFileSync(new URL("../../assets/map/city_manifest.json", import.meta.url), "utf8")) as City;
  assert.equal(city.pickups.length, 100);
  assert.equal(city.hospitals.length, 2);
  const selected = new Set<string>();
  const total = city.pickups.length * city.hospitals.length;
  for (let index = 0; index < total; index++) {
    const pair = randomJourney(city, { pickup: "not-selected", hospital: "not-selected" }, () => (index + 0.5) / total)!;
    assert.ok(city.pickups.some(point => point.id === pair.pickup));
    assert.ok(city.hospitals.some(point => point.id === pair.hospital));
    selected.add(key(pair));
  }
  assert.equal(selected.size, 200);
  for (const pickup of city.pickups)
    for (const hospital of city.hospitals)
      assert.ok(selected.has(key({ pickup: pickup.id, hospital: hospital.id })));
});

test("every alternative occupies one uniform bucket when excluding each possible current pair", () => {
  const city = fixture();
  const all = city.pickups.flatMap(pickup => city.hospitals.map(hospital => ({ pickup: pickup.id, hospital: hospital.id })));
  for (const current of all) {
    const selected = Array.from({ length: all.length - 1 }, (_, index) =>
      key(randomJourney(city, current, () => (index + 0.5) / (all.length - 1))!));
    assert.deepEqual(selected, all.filter(pair => key(pair) !== key(current)).map(key));
    assert.equal(new Set(selected).size, all.length - 1);
  }
});

test("zero and the largest practical random bound select the first and last available pairs", () => {
  const city = fixture();
  assert.deepEqual(randomJourney(city, { pickup: "P001", hospital: "HOSP_WEST" }, () => 0),
    { pickup: "P001", hospital: "HOSP_EAST" });
  assert.deepEqual(randomJourney(city, { pickup: "P001", hospital: "HOSP_WEST" }, () => 1 - Number.EPSILON),
    { pickup: "P002", hospital: "HOSP_EAST" });
  assert.deepEqual(randomJourney(city, { pickup: "P002", hospital: "HOSP_EAST" }, () => 0),
    { pickup: "P001", hospital: "HOSP_WEST" });
  assert.deepEqual(randomJourney(city, { pickup: "P002", hospital: "HOSP_EAST" }, () => 1 - Number.EPSILON),
    { pickup: "P002", hospital: "HOSP_WEST" });
});

test("an unknown current anchor excludes no canonical pair", () => {
  for (const current of [
    { pickup: "unknown", hospital: "HOSP_WEST" },
    { pickup: "P001", hospital: "unknown" },
  ]) {
    assert.deepEqual(randomJourney(fixture(), current, () => 0), { pickup: "P001", hospital: "HOSP_WEST" });
    assert.deepEqual(randomJourney(fixture(), current, () => 1 - Number.EPSILON), { pickup: "P002", hospital: "HOSP_EAST" });
  }
});

test("a sole canonical pair is returned even when it is current, without asking for randomness", () => {
  const current = { pickup: "P001", hospital: "HOSP_WEST" };
  const selected = randomJourney(fixture(["P001"], ["HOSP_WEST"]), current, () => { throw Error("Unexpected RNG call"); });
  assert.deepEqual(selected, current);
  assert.notEqual(selected, current);
});

test("no pickups or no hospitals returns null without invoking the random source", () => {
  for (const city of [fixture([], []), fixture([]), fixture(["P001"], [])])
    assert.equal(randomJourney(city, { pickup: "P001", hospital: "HOSP_WEST" }, () => { throw Error("Unexpected RNG call"); }), null);
});

test("invalid random values fail explicitly instead of returning an invalid anchor", () => {
  for (const value of [NaN, Infinity, -Infinity, -Number.EPSILON, 1, 2, "0.5", null, undefined]) {
    assert.throws(() => randomJourney(fixture(), { pickup: "P001", hospital: "HOSP_WEST" },
      () => value as number), /random source.*\[0, 1\)/);
  }
});

test("selection consumes one random value and leaves the city and current pair unchanged", () => {
  const city = fixture();
  const current = { pickup: "P002", hospital: "HOSP_WEST" };
  const original = structuredClone({ city, current });
  let calls = 0;
  const selected = randomJourney(city, current, () => { calls++; return 0.6; });
  assert.equal(calls, 1);
  assert.notDeepEqual(selected, current);
  assert.deepEqual({ city, current }, original);
});
