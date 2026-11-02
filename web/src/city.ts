import { validateCity } from "./validation.ts";
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
  const city = validateCity(JSON.parse(new TextDecoder().decode(bytes)));
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
