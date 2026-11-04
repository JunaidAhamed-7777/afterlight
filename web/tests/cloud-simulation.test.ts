import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { readSimulationResponse, type SimulationArtifact, type SimulationEvent } from "../src/cloudSimulation.ts";

// Synthetic transport contracts only. These bytes are not a replay, simulator
// output, traffic benchmark, or positive scientific evidence. The recording
// worker independently validates a real replay after this transport boundary.
const REQUEST = "a".repeat(32);
const OTHER = "b".repeat(32);
const HEADERS = { "Content-Type": "application/x-ndjson; charset=utf-8" };
const encoder = new TextEncoder();
const sha = (bytes: Uint8Array) => createHash("sha256").update(bytes).digest("hex");

function fixture() {
  const raw = encoder.encode(JSON.stringify({ synthetic: "transport fixture only", unicode: "Eastbank → Westhaven" }));
  const compressed = gzipSync(raw);
  const first = compressed.subarray(0, 9), second = compressed.subarray(9);
  const accepted = { type: "accepted", request_id: REQUEST };
  const chunks = [first, second].map((block, index) => ({ type: "replay_chunk", index, data: block.toString("base64") }));
  const complete = {
    type: "complete", request_id: REQUEST, chunks: chunks.length,
    compressed_bytes: compressed.byteLength, compressed_sha256: sha(compressed),
    replay_sha256: sha(raw), decoded_bytes: raw.byteLength, scenario_id: "synthetic-transport-contract",
  };
  return { raw, compressed, accepted, chunks, complete };
}

function lines(events: unknown[], trailingNewline = true): Uint8Array {
  return encoder.encode(events.map(event => JSON.stringify(event)).join("\n") + (trailingNewline ? "\n" : ""));
}

function response(events: unknown[], fragmentation = 0, trailingNewline = true): Response {
  const bytes = lines(events, trailingNewline);
  if (!fragmentation) return new Response(bytes, { headers: HEADERS });
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      for (let offset = 0; offset < bytes.length; offset += fragmentation)
        controller.enqueue(bytes.slice(offset, offset + fragmentation));
      controller.close();
    },
  }), { headers: HEADERS });
}

async function readWithoutLeakingUrl(
  value: Response,
  verify: (artifact: SimulationArtifact) => Promise<void> | void = () => {},
  signal: AbortSignal = new AbortController().signal,
  onEvent: (event: SimulationEvent) => void = () => {},
): Promise<void> {
  const artifact = await readSimulationResponse(value, REQUEST, signal, onEvent);
  try { await verify(artifact); }
  finally { URL.revokeObjectURL(artifact.url); }
}

test("fragmented UTF-8 and NDJSON preserve bound identity, callbacks and exact gzip bytes", async () => {
  const f = fixture(), observed: SimulationEvent[] = [];
  const stream = response([
    f.accepted,
    { type: "heartbeat" },
    { type: "progress", phase: "pathfinding", message: "Routing… Eastbank → Westhaven" },
    { type: "route", route_edges: ["edge-first", "edge-last"] },
    ...f.chunks, f.complete,
  ], 1, false);
  await readWithoutLeakingUrl(stream, async artifact => {
    assert.equal(artifact.requestId, REQUEST);
    assert.equal(artifact.replaySha256, sha(f.raw));
    assert.equal(artifact.decodedBytes, f.raw.byteLength);
    assert.equal(artifact.scenarioId, "synthetic-transport-contract");
    const stored = await fetch(artifact.url);
    assert.equal(stored.headers.get("content-type"), "application/gzip");
    assert.deepEqual(new Uint8Array(await stored.arrayBuffer()), new Uint8Array(f.compressed));
  }, new AbortController().signal, event => observed.push(event));
  assert.deepEqual(observed.map(event => event.type), ["accepted", "progress", "route"]);
  assert.equal(observed[1].message, "Routing… Eastbank → Westhaven");
  assert.equal(stream.body!.locked, false);
});

test("one compressed chunk and CRLF messages remain valid with exact compressed SHA", async () => {
  const f = fixture();
  const events = [f.accepted, { type: "replay_chunk", index: 0, data: f.compressed.toString("base64") }, { ...f.complete, chunks: 1 }];
  const body = encoder.encode(events.map(event => JSON.stringify(event)).join("\r\n") + "\r\n");
  await readWithoutLeakingUrl(new Response(body, { headers: HEADERS }), async artifact => {
    assert.equal(sha(new Uint8Array(await (await fetch(artifact.url)).arrayBuffer())), sha(f.compressed));
  });
});

test("out-of-order, duplicated and skipped chunk indices are rejected", async () => {
  const f = fixture();
  for (const chunks of [
    [{ ...f.chunks[0], index: 1 }],
    [f.chunks[0], f.chunks[0]],
    [f.chunks[0], { ...f.chunks[1], index: 2 }],
  ]) await assert.rejects(readWithoutLeakingUrl(response([f.accepted, ...chunks, f.complete])), /out of order/);
});

test("accepted and completion identities must match the requested run, without rebinding", async () => {
  const f = fixture();
  for (const events of [
    [{ ...f.accepted, request_id: OTHER }, ...f.chunks, f.complete],
    [f.accepted, ...f.chunks, { ...f.complete, request_id: OTHER }],
    [f.accepted, f.accepted, ...f.chunks, f.complete],
    [...f.chunks, f.complete],
  ]) await assert.rejects(readWithoutLeakingUrl(response(events)), /identity changed|invalid recording metadata|not bound/);
});

test("correctly formatted but wrong compressed hash never yields a blob URL", async () => {
  const f = fixture();
  await assert.rejects(readWithoutLeakingUrl(response([
    f.accepted, ...f.chunks, { ...f.complete, compressed_sha256: "0".repeat(64) },
  ])), /checksum does not match/);
});

test("completion metadata binds byte and chunk counts, decoded bound, hashes and scenario", async () => {
  const f = fixture();
  for (const change of [
    { chunks: 1 }, { compressed_bytes: f.compressed.byteLength + 1 },
    { decoded_bytes: 0 }, { decoded_bytes: 128 * 1024 * 1024 + 1 },
    { decoded_bytes: true }, { decoded_bytes: 1.5 },
    { compressed_sha256: "not-a-hash" }, { replay_sha256: "not-a-hash" }, { scenario_id: "" },
  ]) await assert.rejects(readWithoutLeakingUrl(response([f.accepted, ...f.chunks, { ...f.complete, ...change }])), /invalid recording metadata/);
  await assert.rejects(readWithoutLeakingUrl(response([f.accepted, { ...f.complete, chunks: 0, compressed_bytes: 0 }])), /invalid recording metadata/);
});

test("EOF without completion and a dropped connection cannot open partial recordings", async () => {
  const f = fixture();
  await assert.rejects(readWithoutLeakingUrl(response([f.accepted, ...f.chunks])), /ended before a complete recording/);
  let pulls = 0;
  const dropped = new Response(new ReadableStream<Uint8Array>({
    pull(controller) {
      if (pulls++ === 0) controller.enqueue(lines([f.accepted, f.chunks[0]]));
      else controller.error(new Error("synthetic connection dropped"));
    },
  }), { headers: HEADERS });
  await assert.rejects(readWithoutLeakingUrl(dropped), /synthetic connection dropped/);
  assert.equal(dropped.body!.locked, false);
});

test("oversized complete and incomplete lines are rejected and cancel their reader", async () => {
  for (const ending of ["", "\n"]) {
    let cancelled = false;
    const oversized = new Response(new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(encoder.encode("x".repeat(128 * 1024 + 1) + ending)); },
      cancel() { cancelled = true; },
    }), { headers: HEADERS });
    await assert.rejects(readWithoutLeakingUrl(oversized), /oversized message/);
    assert.equal(cancelled, true);
    assert.equal(oversized.body!.locked, false);
  }
});

test("cancel while waiting for a server event interrupts the read and releases its reader", { timeout: 2000 }, async () => {
  let cancelled = false;
  const controller = new AbortController();
  const stream = new Response(new ReadableStream<Uint8Array>({
    start(value) { value.enqueue(lines([fixture().accepted])); },
    cancel() { cancelled = true; },
  }), { headers: HEADERS });
  await assert.rejects(readWithoutLeakingUrl(stream, () => {}, controller.signal, event => {
    if (event.type === "accepted") setTimeout(() => controller.abort(), 0);
  }), error => error instanceof DOMException && error.name === "AbortError");
  assert.equal(cancelled, true);
  assert.equal(stream.body!.locked, false);
});

test("an already cancelled request closes the response without consuming events", async () => {
  let cancelled = false, observed = 0;
  const controller = new AbortController();
  controller.abort();
  const stream = new Response(new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } }), { headers: HEADERS });
  await assert.rejects(readWithoutLeakingUrl(stream, () => {}, controller.signal, () => observed++),
    error => error instanceof DOMException && error.name === "AbortError");
  assert.equal(cancelled, true);
  assert.equal(observed, 0);
  assert.equal(stream.body!.locked, false);
});

test("unsupported message types and malformed event shapes are rejected", async () => {
  const f = fixture();
  for (const event of [{ type: "made_up_result" }, [], null, { type: 12 }])
    await assert.rejects(readWithoutLeakingUrl(response([f.accepted, event])), /unsupported message|invalid message/);
});

test("server failure and cancellation events preserve their terminal meaning", async () => {
  const f = fixture();
  await assert.rejects(readWithoutLeakingUrl(response([f.accepted, { type: "error", message: "Worker unavailable; no result exists." }])), /Worker unavailable/);
  await assert.rejects(readWithoutLeakingUrl(response([f.accepted, { type: "cancelled", request_id: REQUEST }])),
    error => error instanceof DOMException && error.name === "AbortError");
});

test("non-progress messages after completion are not silently appended to a recording", async () => {
  const f = fixture();
  await assert.rejects(readWithoutLeakingUrl(response([
    f.accepted, ...f.chunks, f.complete, { type: "route", route_edges: ["late"] },
  ])), /continued after completion/);
});

test("invalid base64 and invalid UTF-8 are rejected before artifact creation", async () => {
  const f = fixture();
  for (const data of ["not base64!", "A", "====", "AA=", "AA==trailing"])
    await assert.rejects(readWithoutLeakingUrl(response([f.accepted, { ...f.chunks[0], data }, f.complete])), /chunks are invalid/);
  const bytes = new Uint8Array([...lines([f.accepted]), 0xc3, 0x28]);
  await assert.rejects(readWithoutLeakingUrl(new Response(bytes, { headers: HEADERS })), /encoded data|UTF-8/i);
});

test("HTTP failures retain safe messages and an HTML success cannot masquerade as NDJSON", async () => {
  await assert.rejects(readWithoutLeakingUrl(new Response(JSON.stringify({ error: "Runner busy. Try later." }), { status: 429 })), /Runner busy/);
  await assert.rejects(readWithoutLeakingUrl(new Response("<html>bad gateway</html>", { status: 502 })), /Simulation unavailable \(502\)/);
  await assert.rejects(readWithoutLeakingUrl(new Response("<html>login</html>", { headers: { "content-type": "text/html" } })), /did not return a progress stream/);
});

test("a failing event consumer still cancels and unlocks the response stream", async () => {
  let cancelled = false;
  const stream = new Response(new ReadableStream<Uint8Array>({
    start(controller) { controller.enqueue(lines([fixture().accepted])); },
    cancel() { cancelled = true; },
  }), { headers: HEADERS });
  await assert.rejects(readWithoutLeakingUrl(stream, () => {}, new AbortController().signal,
    () => { throw new Error("synthetic consumer closed"); }), /consumer closed/);
  assert.equal(cancelled, true);
  assert.equal(stream.body!.locked, false);
});
