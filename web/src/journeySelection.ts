import type { City } from "./types.ts";

export interface JourneySelection {
  pickup: string;
  hospital: string;
}

/** Uniformly choose a canonical pair, excluding the current pair if possible. */
export function randomJourney(
  city: City,
  current: JourneySelection,
  random: () => number = Math.random,
): JourneySelection | null {
  const hospitalCount = city.hospitals.length;
  const total = city.pickups.length * hospitalCount;
  if (!total) return null;
  if (!Number.isSafeInteger(total))
    throw new RangeError("The canonical journey count exceeds the safe integer range.");

  const pickupIndex = city.pickups.findIndex((point) => point.id === current.pickup);
  const hospitalIndex = city.hospitals.findIndex((point) => point.id === current.hospital);
  const currentIndex = pickupIndex < 0 || hospitalIndex < 0
    ? -1
    : pickupIndex * hospitalCount + hospitalIndex;
  const excludeCurrent = total > 1 && currentIndex >= 0;
  const choices = total - Number(excludeCurrent);
  let index = 0;
  if (choices > 1) {
    const value = random();
    if (!Number.isFinite(value) || value < 0 || value >= 1)
      throw new RangeError("The random source must return a finite number in [0, 1).");
    index = Math.floor(value * choices);
  }
  // Skip one flattened pair, rather than retrying or biasing either hospital.
  if (excludeCurrent && index >= currentIndex) index += 1;
  return {
    pickup: city.pickups[Math.floor(index / hospitalCount)].id,
    hospital: city.hospitals[index % hospitalCount].id,
  };
}
