import test from "node:test";
import assert from "node:assert/strict";
import { MAX_JSON_DEPTH, parseJsonBytes } from "../src/strictJson.ts";
import { boundedJson } from "../src/response.ts";
const bytes = (text: string) => new TextEncoder().encode(text);
const parse = (text: string) => parseJsonBytes(bytes(text));

test("container depth includes the root and rejects 65 before native parsing", () => {
  const nested = (depth: number) => "[".repeat(depth) + "0" + "]".repeat(depth);
  assert.doesNotThrow(() => parse(nested(MAX_JSON_DEPTH)));
  assert.throws(() => parse(nested(MAX_JSON_DEPTH + 1)), /depth 64/);
  assert.throws(() => parse("[".repeat(65)), /depth 64/);
  assert.doesNotThrow(() => parse('{"extra":' + nested(63) + '}'));
  assert.throws(() => parse('{"extra":' + nested(64) + '}'), /depth 64/);
});

test("quoted brackets, escaped quotes and odd/even backslash runs are data", () => {
  for (const value of ["[".repeat(100), '"' + "}".repeat(100), "\\", '\\"[{', '\\\\"}]', "snow 雪 🚑"]) {
    assert.equal(parse(JSON.stringify(value)), value);
  }
  assert.deepEqual(parse(String.raw`{"escaped":"\u005b\u007b\u0022\u005c","real":[]}`),
    { escaped: '[{"\\', real: [] });
});

test("strict UTF-8 accepts a BOM but does not alter original bytes", () => {
  const input = new Uint8Array([0xef, 0xbb, 0xbf, ...bytes('{"ok":true}')]);
  const original = input.slice();
  assert.deepEqual(parseJsonBytes(input), { ok: true });
  assert.deepEqual(input, original);
  for (const malformed of [[0xff], [0x22, 0xc3, 0x28, 0x22], [0x22, 0xe2, 0x82]])
    assert.throws(() => parseJsonBytes(new Uint8Array(malformed)), /UTF-8/);
});

test("whole-value finite check rejects overflow in otherwise ignored extras", () => {
  for (const text of ['1e309', '-1e309', '{"provenance":{"extra":[1e309]}}', '[{"x":-1e999}]'])
    assert.throws(() => parse(text), /nonfinite/);
  assert.deepEqual(parse('{"value":1e308,"underflow":1e-999,"text":"1e309"}'),
    { value: 1e308, underflow: 0, text: "1e309" });
  for (const malformed of ['NaN', 'Infinity', '{"x":}', '[}', '{"x":"unterminated}'])
    assert.throws(() => parse(malformed));
});

test("bounded JSON cancels an oversized chunked body before decoding", async () => {
  let canceled = false;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) { controller.enqueue(new Uint8Array(1024 * 1024)); },
    cancel() { canceled = true; },
  });
  await assert.rejects(boundedJson(new Response(body)), /size limit/);
  assert.equal(canceled, true);
});

test("bounded JSON applies strict parsing after streaming", async () => {
  await assert.rejects(boundedJson(new Response(bytes('{"extra":1e309}'))), /nonfinite/);
  await assert.rejects(boundedJson(new Response(new Uint8Array([0xff]))), /UTF-8/);
  assert.deepEqual(await boundedJson(new Response(bytes('{"ok":[]}'))), { ok: [] });
});
