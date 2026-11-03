import type { World } from "./types.ts";

export interface CivilianTailDisplay {
  value: string;
  population: string;
}

/** Descriptive within-world tail only. Never derive a policy gain or fill missing data. */
export function civilianTailDisplay(world: Pick<World, "status" | "metrics">): CivilianTailDisplay {
  const metrics = world.metrics;
  const valuePresent = Object.hasOwn(metrics, "civilian_excess_p95_s");
  const populationPresent = Object.hasOwn(metrics, "civilian_excess_p95_population");
  if (!valuePresent && !populationPresent)
    return { value: "Not recorded", population: "This recording does not include this optional measure." };
  const unavailable = { value: "Unavailable", population: "Requires a valid completed world and every scheduled civilian to finish." };
  const value = metrics.civilian_excess_p95_s;
  const raw = metrics.civilian_excess_p95_population;
  if (world.status !== "completed" || typeof value !== "number" || !Number.isFinite(value) || value < 0 ||
      !raw || typeof raw !== "object" || Array.isArray(raw)) return unavailable;
  const population = raw as Record<string, unknown>;
  const count = population.scheduled_count;
  if (typeof count !== "number" || !Number.isSafeInteger(count) || count <= 0 ||
      population.completed_count !== count || population.included_count !== count ||
      population.scope !== "all_scheduled_civilian_vehicles_in_this_world" ||
      population.percentile !== 95 || population.method !== "nearest_rank_ceil_p_times_n_no_interpolation" ||
      population.eligibility !== "valid_completed_world_all_civilians_completed_nonempty" ||
      population.value_definition !== "max(0, arrival_s - scheduled_departure_s - per_vehicle_reference_s)" ||
      population.reference !== "saved demand external-lane free-flow lower bound; excludes internal junctions and acceleration" ||
      population.units !== "seconds" || population.ambulance_excluded !== true) return unavailable;
  if (Object.hasOwn(metrics, "accounting")) {
    const accounting = metrics.accounting;
    if (!accounting || typeof accounting !== "object" || Array.isArray(accounting)) return unavailable;
    const counts = accounting as Record<string, unknown>;
    if (counts.scheduled !== count || counts.completed !== count) return unavailable;
  }
  return { value: `${value.toFixed(2)} s`, population: `All ${count} scheduled civilians completed and included; ambulance excluded.` };
}
