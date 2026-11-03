import { parseJsonBytes } from "./strictJson.ts";
import { boundedBytes } from "./response.ts";
import type { CatalogEntry, Replay } from "./types.ts";
import { validateReplay } from "./replay.ts";
export type PublishedEntry = CatalogEntry & { sha256?: string; bytes?: number };
export function bindRecording(replay: Replay, entry: CatalogEntry): Replay {
  const scenario = replay.scenario;
  if (
    scenario.id !== entry.id ||
    scenario.seed !== entry.seed ||
    scenario.pickup_id !== entry.pickup_id ||
    scenario.hospital_id !== entry.hospital_id ||
    replay.duration_s !== entry.duration_s ||
    replay.worlds.afterlight.policy !== entry.policy ||
    (entry.lead_s !== undefined && replay.worlds.afterlight.lead_s !== entry.lead_s)
  )
    throw new Error(
      "The fetched recording does not match the selected experiment. Refresh the library before retrying.",
    );
  return replay;
}
export async function loadRecording(
  entry: PublishedEntry,
  url: string,
  signal: AbortSignal,
): Promise<Replay> {
  const response = await fetch(url, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
    cache: "no-cache",
  });
  if (!response.ok)
    throw new Error(
      `Recording request failed (${response.status}). Retry the selected experiment.`,
    );
  const bytes = await boundedBytes(response);
  if (entry.bytes !== undefined && entry.bytes !== bytes.byteLength)
    throw new Error(
      "The recording byte count does not match its published manifest.",
    );
  if (entry.sha256 !== undefined) {
    if (!/^[a-f0-9]{64}$/i.test(entry.sha256))
      throw new Error("The recording catalog has an invalid checksum.");
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const actual = Array.from(new Uint8Array(digest), (b) =>
      b.toString(16).padStart(2, "0"),
    ).join("");
    if (actual !== entry.sha256.toLowerCase())
      throw new Error(
        "The recording checksum does not match its published manifest. No outcomes will be displayed.",
      );
  }
  return bindRecording(
    validateReplay(parseJsonBytes(bytes)),
    entry,
  );
}
