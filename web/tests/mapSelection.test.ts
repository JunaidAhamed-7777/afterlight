import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import type { City } from "../src/types.ts";
import { MapSelectionLayer } from "../src/MapSelectionLayer.ts";
// Canonical-coordinate CPU fixtures only. No WebGL, traffic or outcome evidence.
const city = {
  pickups: [
    { id: "P001", road_id: "R1", position: [12, 25, 3] },
    { id: "P002", road_id: "R2", position: [-40, -20, 0] },
  ],
  hospitals: [
    { id: "HOSP_WEST", name: "Westhaven", driveway_anchor: [55, 10, 0] },
    { id: "HOSP_EAST", name: "Eastbank", driveway_anchor: [-55, -10, 2] },
  ],
} as unknown as City;
function camera(perspective: boolean, roll = 0) {
  const result = perspective ? new THREE.PerspectiveCamera(42, 1.5, 1, 1000)
    : new THREE.OrthographicCamera(-100, 100, 70, -70, 1, 1000);
  result.position.set(150, 180, 220);
  result.lookAt(0, 0, 0);
  result.rotateZ(roll);
  result.updateProjectionMatrix(); result.updateMatrixWorld(true);
  return result;
}
test("one instanced marker layer transforms actual canonical curb anchors once", () => {
  const layer = new MapSelectionLayer(); layer.setAnchors(city, "pickup");
  layer.update(camera(true), 800);
  assert.ok(layer.mesh instanceof THREE.InstancedMesh);
  assert.equal(layer.mesh.count, 2);
  const matrix = new THREE.Matrix4(); layer.mesh.getMatrixAt(0, matrix);
  const position = new THREE.Vector3().setFromMatrixPosition(matrix);
  assert.deepEqual(position.toArray(), [12, 5, -25]);
  const scale = new THREE.Vector3().setFromMatrixScale(matrix);
  assert.ok(scale.x > 0 && Math.abs(scale.x-scale.y) < 1e-6);
  layer.dispose();
});
for (const [label, perspective, roll] of [
  ["orthographic", false, 0], ["perspective", true, 0], ["rolled perspective", true, Math.PI/3],
] as const) {
  test(`ray picks exact canonical ID using ${label} render camera`, () => {
    const layer = new MapSelectionLayer(); const view = camera(perspective, roll);
    layer.setAnchors(city, "pickup"); layer.update(view, 800);
    for (const anchor of layer.projectedAnchors(view)) {
      assert.equal(layer.pick(anchor.ndc[0], anchor.ndc[1], view)?.id, anchor.id);
    }
    assert.equal(layer.pick(4, 4, view), null);
    layer.dispose();
  });
}
test("hospital mode uses driveway anchors and exiting removes all picking targets", () => {
  const layer = new MapSelectionLayer(); const view = camera(true, 0.4);
  layer.setAnchors(city, "pickup"); layer.update(view, 800);
  layer.setAnchors(city, "hospital"); layer.update(view, 800);
  const rows = layer.projectedAnchors(view);
  assert.deepEqual(rows.map(row => row.id), ["HOSP_WEST", "HOSP_EAST"]);
  assert.equal(layer.pick(rows[0].ndc[0], rows[0].ndc[1], view)?.label, "Westhaven");
  const matrix = new THREE.Matrix4(); layer.mesh.getMatrixAt(1, matrix);
  assert.deepEqual(new THREE.Vector3().setFromMatrixPosition(matrix).toArray(), [-55, 4, 10]);
  layer.setAnchors(city, null);
  assert.equal(layer.mesh.visible, false); assert.equal(layer.mesh.count, 0);
  assert.equal(layer.pick(rows[0].ndc[0], rows[0].ndc[1], view), null);
  layer.dispose();
});
test("missing city creates no substitute markers, excess capacity fails clearly", () => {
  const layer = new MapSelectionLayer(); layer.setAnchors(null, "pickup");
  assert.equal(layer.mesh.count, 0);
  const oversized = { ...city, pickups: Array.from({ length: 101 }, (_, i) => ({ ...city.pickups[0], id: `P${i}` })) };
  assert.throws(() => layer.setAnchors(oversized, "pickup"), /capacity/);
  assert.throws(() => layer.setAnchors(oversized, "pickup"), /capacity/, "invalid input must not poison the identity cache");
  assert.equal(layer.mesh.count, 0);
  layer.setAnchors(city, "pickup");
  layer.update(camera(true), 800);
  assert.equal(layer.mesh.count, 2);
  assert.equal(layer.mesh.visible, true);
  layer.dispose();
});
test("selection resources detach and dispose without touching unrelated scene objects", () => {
  const scene = new THREE.Scene(); const layer = new MapSelectionLayer();
  const unrelated = new THREE.Group(); scene.add(unrelated, layer.mesh);
  let geometryDisposed = false, materialDisposed = false;
  layer.mesh.geometry.addEventListener("dispose", () => { geometryDisposed = true; });
  layer.mesh.material.addEventListener("dispose", () => { materialDisposed = true; });
  layer.dispose();
  assert.equal(layer.mesh.parent, null); assert.equal(unrelated.parent, scene);
  assert.ok(geometryDisposed && materialDisposed);
});
