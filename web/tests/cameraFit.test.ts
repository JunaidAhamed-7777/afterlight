import test from "node:test";
import assert from "node:assert/strict";
import { fitOrthographic } from "../src/cameraFit.ts";
// Camera-space corner fixtures only, not renderer/GPU performance evidence.
const corners: Array<[number, number]> = [[-920,-670],[-920,670],[920,-670],[920,670]];
for (const [label,width,height] of [
  ["desktop",1280,760], ["mobile portrait",360,740],
  ["tall generation layout",720,1500], ["narrow split view",280,1000],
  ["wide landscape",1440,400],
] as const) {
  test(`overview contains all corners with padding: ${label}`, () => {
    const fit = fitOrthographic(corners,width,height);
    for (const [x,y] of corners) {
      assert.ok(Math.abs(x)/fit.halfWidth <= 1/1.18 + 1e-12);
      assert.ok(Math.abs(y)/fit.halfHeight <= 1/1.18 + 1e-12);
    }
    assert.ok(Math.abs(fit.halfWidth/fit.halfHeight-width/height)<1e-12);
  });
}
test("resize fits narrower aspect instead of clipping horizontal extent", () => {
  const desktop = fitOrthographic(corners,1280,760);
  const mobile = fitOrthographic(corners,360,740);
  assert.ok(mobile.halfHeight > desktop.halfHeight);
  assert.ok(mobile.halfWidth >= 920*1.18);
});
test("off-center bounds remain contained and invalid viewport fails closed", () => {
  const fit = fitOrthographic([[-100,30],[1100,500]],300,900);
  assert.ok(fit.halfWidth >= 1100*1.18);
  assert.throws(() => fitOrthographic(corners,0,700));
  assert.throws(() => fitOrthographic([[NaN,1]],300,700));
});

test("finite inputs that overflow derived extents fail deterministically", () => {
  assert.throws(() => fitOrthographic(corners, Number.MAX_VALUE, Number.MIN_VALUE), /numeric extents/);
  assert.throws(() => fitOrthographic([[Number.MAX_VALUE, 1]], 1, 1), /numeric extents/);
});
