import test from "node:test";
import assert from "node:assert/strict";
import { gzipSync } from "node:zlib";
import { recordingBytes } from "../src/recording.ts";

test("gzip transport reconstructs exact original UTF-8 bytes; decoded HTTP bodies are not decoded twice", async () => {
  const source = new TextEncoder().encode(
    '{"label":"Ambulance → hospital", "sample":0.5}',
  );
  for (const wire of [source, new Uint8Array(gzipSync(source))]) {
    const bytes = await recordingBytes(new Response(wire));
    assert.deepEqual(bytes, source);
    assert.equal(
      await crypto.subtle
        .digest("SHA-256", bytes)
        .then((v) => Buffer.from(v).toString("hex")),
      await crypto.subtle
        .digest("SHA-256", source)
        .then((v) => Buffer.from(v).toString("hex")),
    );
  }
});
test("decoded size limit cancels a compressed expansion before parsing", async () => {
  const wire = new Uint8Array(gzipSync("x".repeat(100_000)));
  assert.ok(wire.byteLength < 500);
  await assert.rejects(recordingBytes(new Response(wire), 500), /size limit/);
});
test("corrupt gzip produces a recoverable recording error", async () => {
  await assert.rejects(
    recordingBytes(new Response(new Uint8Array([0x1f, 0x8b, 0, 0, 1]))),
    /could not be decoded/,
  );
});
