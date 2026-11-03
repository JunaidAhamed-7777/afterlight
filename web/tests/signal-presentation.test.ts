import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { GeometryLayer, signalColor, signalSymbolScale } from "../src/GeometryLayer.ts";
import type { SignalGeometry } from "../src/types.ts";
const signals: SignalGeometry[] = [{ id: "J1", position: [0,0], links: [0,1,2].map(index => ({
  index, from_edge: "in", to_edge: "out"+index, from_lane: "in_0", to_lane: "out_0",
  incoming_shape: [[0,-30],[0,0]], outgoing_shape: [[0,0],[30,0]], stop_line: [0,0], turn: "r", via_lane: null,
})) }];
function camera() {
  const view = new THREE.OrthographicCamera(-100,100,100,-100,.1,2000);
  view.position.set(0,200,100); view.lookAt(0,0,0); view.updateMatrixWorld(true); return view;
}
test("signal overlays use two batches and preserve each controlled-link state", () => {
  const layer = new GeometryLayer(); layer.setGeometry(null, [], signals);
  assert.equal(layer.group.children.length,2);
  const arrows = layer.group.getObjectByName("Per-controlled-link signal arrows") as THREE.InstancedMesh;
  const backs = layer.group.getObjectByName("Signal contrast outlines") as THREE.InstancedMesh;
  layer.update([{id:"J1",state:"rGy"}]); layer.updatePresentation(camera(),800);
  assert.equal(arrows.count,3); assert.equal(backs.count,3);
  const color = new THREE.Color();
  for (const [i,state] of [..."rGy"].entries()) {
    arrows.getColorAt(i,color); assert.equal(color.getHex(),new THREE.Color(signalColor(state)).getHex());
  }
  const matrix = new THREE.Matrix4(); arrows.getMatrixAt(1,matrix);
  const base = new THREE.Vector3().applyMatrix4(matrix);
  const tip = new THREE.Vector3(0,-3.5,0).applyMatrix4(matrix);
  assert.ok(tip.x > base.x, "outgoing east arrow retains its actual lane direction");
  assert.ok(Math.abs(tip.z-base.z)<1e-6);
  assert.equal((arrows.material as THREE.MeshBasicMaterial).depthWrite,false);
  layer.update([]); layer.updatePresentation(camera(),800);
  assert.equal(arrows.count,0); assert.equal(backs.count,0);
  layer.dispose(); assert.equal(layer.group.children.length,0);
});
test("screen scale increases at overview but is bounded and close zoom remains readable", () => {
  assert.ok(signalSymbolScale(1000,800)>signalSymbolScale(100,800));
  assert.equal(signalSymbolScale(100000,800),3);
  assert.equal(signalSymbolScale(1,800),.3);
  assert.equal(signalSymbolScale(NaN,800),1);
  assert.equal(signalColor("o"),"#B4C1CE");
});
test("geometry refresh replaces signal instances without retaining old movement identities", () => {
  const layer = new GeometryLayer(); layer.setGeometry(null,[],signals);
  layer.setGeometry(null,[],[]); layer.update([{id:"J1",state:"GGG"}]);
  layer.updatePresentation(camera(),800); assert.equal(layer.group.children.length,0);
  layer.dispose();
});
