import test from "node:test";
import assert from "node:assert/strict";
import { geometryMatches } from "../src/city.ts";
test("only exact canonical map byte hashes enable city overlay", () => {
  assert.equal(geometryMatches("a".repeat(64), "a".repeat(64)), true);
  assert.equal(geometryMatches("a".repeat(64), "b".repeat(64)), false);
  assert.equal(geometryMatches(undefined, "a".repeat(64)), false);
  assert.equal(geometryMatches("a".repeat(64), ""), false);
});
