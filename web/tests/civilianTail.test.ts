import test from "node:test";
import assert from "node:assert/strict";
import { civilianTailDisplay } from "../src/civilianTail.ts";

function recorded() {
  return { status: "completed", metrics: {
    civilian_excess_p95_s: 12.345,
    civilian_excess_p95_population: {
      scope: "all_scheduled_civilian_vehicles_in_this_world",
      scheduled_count: 20, completed_count: 20, included_count: 20,
      percentile: 95, method: "nearest_rank_ceil_p_times_n_no_interpolation",
      eligibility: "valid_completed_world_all_civilians_completed_nonempty",
      value_definition: "max(0, arrival_s - scheduled_departure_s - per_vehicle_reference_s)",
      reference: "saved demand external-lane free-flow lower bound; excludes internal junctions and acceleration",
      units: "seconds", ambulance_excluded: true,
    },
  } };
}

test("individual tail is descriptive seconds with complete population, not a gain", () => {
  assert.deepEqual(civilianTailDisplay(recorded()), {
    value: "12.35 s", population: "All 20 scheduled civilians completed and included; ambulance excluded.",
  });
  const zero = recorded(); zero.metrics.civilian_excess_p95_s = 0;
  assert.equal(civilianTailDisplay(zero).value, "0.00 s");
});

test("legacy absence differs from unavailable or invalid outcomes", () => {
  assert.equal(civilianTailDisplay({ status: "completed", metrics: {} }).value, "Not recorded");
  for (const status of ["invalid", "censored", "infrastructure_error"]) {
    const world = recorded(); world.status = status;
    assert.equal(civilianTailDisplay(world).value, "Unavailable");
  }
  for (const value of [null, undefined, NaN, Infinity, -1, "12", true]) {
    const world = recorded(); (world.metrics as Record<string, unknown>).civilian_excess_p95_s = value;
    assert.equal(civilianTailDisplay(world).value, "Unavailable");
  }
});

test("partial or misdescribed populations never appear as all-civilian tails", () => {
  for (const [key, value] of Object.entries({
    scheduled_count: 0, completed_count: 19, included_count: 19,
    reference: "includes acceleration", scope: "completed_only", eligibility: "partial", value_definition: "arrival minus insertion", percentile: 50, method: "interpolation", units: "ms", ambulance_excluded: false,
  })) {
    const world = recorded();
    (world.metrics.civilian_excess_p95_population as Record<string, unknown>)[key] = value;
    assert.equal(civilianTailDisplay(world).value, "Unavailable");
  }
  for (const population of [null, [], "population", undefined]) {
    const world = recorded();
    (world.metrics as Record<string, unknown>).civilian_excess_p95_population = population;
    assert.equal(civilianTailDisplay(world).value, "Unavailable");
  }
});


test("optional accounting cannot contradict the declared tail population", () => {
  const matched = recorded();
  (matched.metrics as Record<string, unknown>).accounting = { scheduled: 20, completed: 20 };
  assert.equal(civilianTailDisplay(matched).value, "12.35 s");
  for (const accounting of [null, [], {}, { scheduled: 21, completed: 20 }, { scheduled: 20, completed: 19 }]) {
    const world = recorded();
    (world.metrics as Record<string, unknown>).accounting = accounting;
    assert.equal(civilianTailDisplay(world).value, "Unavailable");
  }
});
