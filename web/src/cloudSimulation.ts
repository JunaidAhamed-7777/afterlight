import { boundedBytes } from "./response.ts";
import { parseJsonBytes } from "./strictJson.ts";

export type SimulationEvent = Record<string, unknown> & { type: string };
export interface SimulationArtifact {
  url: string;
  requestId: string;
  replaySha256: string;
  decodedBytes: number;
  scenarioId: string;
}
const MAX_LINE = 128 * 1024;
const MAX_WIRE = 32 * 1024 * 1024;
const MAX_GZIP = 20 * 1024 * 1024;
const MAX_REPLAY = 128 * 1024 * 1024;
const hash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const size = (value: unknown, maximum: number): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value > 0 && value <= maximum;

/** Strict, bounded streamed transport. Original replay validation stays in the recording worker. */
export async function readSimulationResponse(
  response: Response,
  requestId: string,
  signal: AbortSignal,
  onEvent: (event: SimulationEvent) => void,
): Promise<SimulationArtifact> {
  if (!response.ok) {
    let message = `Simulation unavailable (${response.status}). Try again.`;
    try {
      const body = parseJsonBytes(await boundedBytes(response, 4096)) as { error?: unknown };
      if (typeof body.error === "string") message = body.error;
    } catch { /* An infrastructure error may have a non-JSON response. */ }
    throw new Error(message);
  }
  if (!response.headers.get("content-type")?.includes("application/x-ndjson") || !response.body)
    throw new Error("The simulation server did not return a progress stream.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const blocks: Uint8Array<ArrayBuffer>[] = [];
  let wireBytes = 0, gzipBytes = 0, pending = "", accepted = false;
  let completion: SimulationEvent | null = null;
  const abort = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener("abort", abort, { once: true });
  const consume = (line: string) => {
    if (!line.trim()) return;
    if (line.length > MAX_LINE) throw new Error("The simulation stream contains an oversized message.");
    const value = parseJsonBytes(new TextEncoder().encode(line), MAX_LINE);
    if (!value || typeof value !== "object" || Array.isArray(value) || typeof (value as SimulationEvent).type !== "string")
      throw new Error("The simulation stream contains an invalid message.");
    const event = value as SimulationEvent;
    if (event.type === "heartbeat") return;
    if (completion) throw new Error("The simulation stream continued after completion.");
    if (event.type === "accepted") {
      if (accepted || event.request_id !== requestId) throw new Error("The simulation request identity changed.");
      accepted = true;
    } else {
      if (!accepted) throw new Error("The simulation stream was not bound to this request.");
      if (event.type === "error") throw new Error(typeof event.message === "string" ? event.message : "The simulation could not finish. Try another journey.");
      if (event.type === "cancelled") throw new DOMException("Simulation canceled.", "AbortError");
      if (event.type === "replay_chunk") {
        if (event.index !== blocks.length || typeof event.data !== "string" ||
          !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(event.data))
          throw new Error("The simulation recording chunks are invalid or out of order.");
        const binary = atob(event.data);
        const block = Uint8Array.from(binary, character => character.charCodeAt(0));
        gzipBytes += block.byteLength;
        if (gzipBytes > MAX_GZIP) throw new Error("The generated recording exceeds the supported size.");
        blocks.push(block);
      } else if (event.type === "complete") {
        if (event.request_id !== requestId || event.chunks !== blocks.length || !blocks.length ||
          event.compressed_bytes !== gzipBytes || !hash(event.compressed_sha256) || !hash(event.replay_sha256) ||
          !size(event.decoded_bytes, MAX_REPLAY) || typeof event.scenario_id !== "string" || !event.scenario_id)
          throw new Error("The completed simulation has invalid recording metadata.");
        completion = event;
      } else if (event.type !== "progress" && event.type !== "route")
        throw new Error("The simulation stream contains an unsupported message.");
    }
    if (event.type !== "replay_chunk" && event.type !== "complete") onEvent(event);
  };
  try {
    signal.throwIfAborted();
    while (true) {
      const { done, value } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      wireBytes += value.byteLength;
      if (wireBytes > MAX_WIRE) throw new Error("The simulation stream exceeds the supported size.");
      pending += decoder.decode(value, { stream: true });
      let newline: number;
      while ((newline = pending.indexOf("\n")) >= 0) {
        consume(pending.slice(0, newline));
        pending = pending.slice(newline + 1);
      }
      if (pending.length > MAX_LINE) throw new Error("The simulation stream contains an oversized message.");
    }
    pending += decoder.decode();
    if (pending.trim()) consume(pending);
    if (!completion) throw new Error("The simulation connection ended before a complete recording arrived. Try again.");
    const bytes = new Uint8Array(gzipBytes);
    let offset = 0;
    for (const block of blocks) { bytes.set(block, offset); offset += block.byteLength; }
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), n => n.toString(16).padStart(2, "0")).join("");
    if (digest !== completion.compressed_sha256) throw new Error("The generated recording checksum does not match. No results were opened.");
    signal.throwIfAborted();
    return {
      url: URL.createObjectURL(new Blob([bytes], { type: "application/gzip" })),
      requestId,
      replaySha256: completion.replay_sha256 as string,
      decodedBytes: completion.decoded_bytes as number,
      scenarioId: completion.scenario_id as string,
    };
  } finally {
    signal.removeEventListener("abort", abort);
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
