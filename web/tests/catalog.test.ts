import test from "node:test";
import assert from "node:assert/strict";
import { recordingUrl, validateCatalog } from "../src/catalog.ts";
const base = "http://127.0.0.1:5173/replays/";
const row = {
  id: "a",
  title: "Run A",
  url: "a.json",
  seed: 1,
  pickup_id: "P001",
  hospital_id: "HOSP_WEST",
  policy: "fixed",
  duration_s: 100,
};
test("relative recording paths remain on configured origin", () =>
  assert.equal(
    recordingUrl("a.json", base),
    "http://127.0.0.1:5173/replays/a.json",
  ));
test("cross-origin and javascript URLs rejected", () => {
  for (const url of [
    "https://example.com/trace.json",
    "javascript:alert(1)",
    "//example.com/a.json",
  ])
    assert.throws(() => recordingUrl(url, base), /origin/);
});
test("credentials in recording links rejected", () =>
  assert.throws(
    () => recordingUrl("http://u:p@127.0.0.1:5173/a", base),
    /origin/,
  ));
test("empty catalogs are valid and do not manufacture recordings", () =>
  assert.deepEqual(
    validateCatalog({ schema: "afterlight.catalog.v1", runs: [] }, base),
    [],
  ));
test("duplicate IDs rejected before selection", () =>
  assert.throws(
    () =>
      validateCatalog(
        { schema: "afterlight.catalog.v1", runs: [row, row] },
        base,
      ),
    /duplicate/,
  ));
test("incomplete rows rejected", () =>
  assert.throws(
    () =>
      validateCatalog(
        {
          schema: "afterlight.catalog.v1",
          runs: [{ ...row, duration_s: null }],
        },
        base,
      ),
    /incomplete/,
  ));
