import test from "node:test";
import assert from "node:assert/strict";
import { boundedBytes } from "../src/response.ts";
test("streaming limit cancels an oversized response without Content-Length", async () => {
  let canceled = false;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) { controller.enqueue(new Uint8Array(4)); },
    cancel() { canceled = true; },
  });
  await assert.rejects(boundedBytes(new Response(body), 7), /size limit/);
  assert.equal(canceled, true);
});
test("exact-limit chunked response is preserved", async () => {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new Uint8Array([1,2]));
      controller.enqueue(new Uint8Array([3]));
      controller.close();
    },
  });
  assert.deepEqual(await boundedBytes(new Response(body), 3), new Uint8Array([1,2,3]));
});
test("oversized declared body is canceled before reading", async () => {
  let canceled = false;
  const body = new ReadableStream<Uint8Array>({cancel() { canceled = true; }});
  await assert.rejects(boundedBytes(new Response(body, {headers:{'Content-Length':'8'}}), 7), /size limit/);
  assert.equal(canceled, true);
});
