import { parseJsonBytes } from "./strictJson.ts";
import { MAX_JSON_BYTES } from "./strictJson.ts";
import { boundedBytes } from "./response.ts";
import type { CatalogEntry, Replay } from "./types.ts";
import { validateReplay } from "./replay.ts";
export type PublishedEntry = CatalogEntry & { sha256?: string; bytes?: number };
/** Lossless transport only. Published checksums always bind decoded original bytes. */
export async function recordingBytes(
  response: Response,
  limit = MAX_JSON_BYTES,
): Promise<Uint8Array<ArrayBuffer>> {
  const bytes = await boundedBytes(response, limit);
  if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) return bytes;
  if (typeof DecompressionStream === "undefined")
    throw new Error(
      "This browser cannot open compressed recordings. Open the viewer in a current desktop browser.",
    );
  try {
    const decoded = new Blob([bytes])
      .stream()
      .pipeThrough(new DecompressionStream("gzip"));
    // Bound the decoded stream as well as the wire body, including a gzip bomb.
    return await boundedBytes(new Response(decoded), limit);
  } catch (error) {
    if (error instanceof Error && /size limit/.test(error.message)) throw error;
    throw new Error(
      "The compressed recording could not be decoded. Retry the recording.",
    );
  }
}
export function bindRecording(replay: Replay, entry: CatalogEntry): Replay {
  const scenario = replay.scenario;
  if (
    scenario.id !== entry.id ||
    scenario.seed !== entry.seed ||
    scenario.pickup_id !== entry.pickup_id ||
    scenario.hospital_id !== entry.hospital_id ||
    replay.duration_s !== entry.duration_s ||
    replay.worlds.afterlight.policy !== entry.policy ||
    (entry.lead_s !== undefined &&
      replay.worlds.afterlight.lead_s !== entry.lead_s)
  )
    throw new Error(
      "The fetched recording does not match the selected experiment. Refresh the library before retrying.",
    );
  return replay;
}
export async function loadRecordingDirect(
  entry: PublishedEntry | null,
  url: string,
  signal: AbortSignal,
  expectedSha256?: string,
  decodedLimit = MAX_JSON_BYTES,
): Promise<Replay> {
  const response = await fetch(url, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
    cache: "no-cache",
  });
  if (!response.ok)
    throw new Error(
      `Recording request failed (${response.status}). Retry the selected experiment.`,
    );
  const bytes = await recordingBytes(response, decodedLimit);
  if (entry?.bytes !== undefined && entry.bytes !== bytes.byteLength)
    throw new Error(
      "The recording byte count does not match its published manifest.",
    );
  const checksum = entry?.sha256 ?? expectedSha256;
  if (checksum !== undefined) {
    if (!/^[a-f0-9]{64}$/i.test(checksum))
      throw new Error("The recording catalog has an invalid checksum.");
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const actual = Array.from(new Uint8Array(digest), (b) =>
      b.toString(16).padStart(2, "0"),
    ).join("");
    if (actual !== checksum.toLowerCase())
      throw new Error(
        "The recording checksum does not match its published manifest. No outcomes will be displayed.",
      );
  }
  const replay = validateReplay(parseJsonBytes(bytes, decodedLimit));
  return entry ? bindRecording(replay, entry) : replay;
}
