import type { City } from "./types.ts";
export async function loadCanonicalCity(
  url: string,
  signal: AbortSignal,
): Promise<{ city: City; sha256: string }> {
  const response = await fetch(url, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
  });
  if (!response.ok)
    throw new Error(`City map request failed (${response.status}).`);
  const bytes = await response.arrayBuffer();
  const city = JSON.parse(new TextDecoder().decode(bytes)) as City;
  if (
    city.schema !== "afterlight.city.v1" ||
    !Array.isArray(city.nodes) ||
    !Array.isArray(city.edges) ||
    !Array.isArray(city.pickups) ||
    !Array.isArray(city.hospitals)
  )
    throw new Error("The canonical city map has an unsupported format.");
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const sha256 = Array.from(new Uint8Array(digest), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
  return { city, sha256 };
}
export function geometryMatches(
  replayHash: unknown,
  cityHash: string,
): boolean {
  return (
    typeof replayHash === "string" &&
    /^[a-f0-9]{64}$/i.test(replayHash) &&
    cityHash.length === 64 &&
    replayHash.toLowerCase() === cityHash.toLowerCase()
  );
}
