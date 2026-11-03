import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { VehicleLayer } from "../src/VehicleLayer.ts";
function close(actual: number, expected: number) {
  assert.ok(Math.abs(actual - expected) < 1e-5, `${actual} != ${expected}`);
}
test("vehicle-only bounds normalization matches recorded front bumper and width", () => {
  const template = new THREE.Group();
  template.position.set(12, 0, 8);
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(2, 2, 4),
    new THREE.MeshBasicMaterial(),
  );
  mesh.position.y = 1;
  template.add(mesh);
  const layer = new VehicleLayer();
  layer.update(
    [
      {
        id: "ambulance",
        type: "ambulance",
        x: 100,
        y: 200,
        z: 0,
        angle_deg: 0,
        speed_mps: 0,
        length_m: 8,
        width_m: 3,
      },
    ],
    new Map([["ambulance", template]]),
  );
  const instance = layer.group.children[0] as THREE.InstancedMesh;
  const matrix = new THREE.Matrix4();
  instance.getMatrixAt(0, matrix);
  instance.geometry.computeBoundingBox();
  const bounds = instance.geometry.boundingBox!.clone().applyMatrix4(matrix);
  close(bounds.min.z, -200);
  close(bounds.max.z, -192);
  close(bounds.min.x, 98.5);
  close(bounds.max.x, 101.5);
  assert.deepEqual(template.position.toArray(), [12, 0, 8]);
  layer.dispose();
  mesh.geometry.dispose();
  (mesh.material as THREE.Material).dispose();
});
test("eastbound transformed model nose agrees with the same front-bumper contract", () => {
  const template = new THREE.Group();
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(2, 2, 4),
    new THREE.MeshBasicMaterial(),
  );
  template.add(mesh);
  const layer = new VehicleLayer();
  layer.update(
    [
      {
        id: "car",
        type: "car",
        x: 100,
        y: 200,
        z: 0,
        angle_deg: 90,
        speed_mps: 0,
        length_m: 8,
      },
    ],
    new Map([["car", template]]),
  );
  const instance = layer.group.children[0] as THREE.InstancedMesh;
  const matrix = new THREE.Matrix4();
  instance.getMatrixAt(0, matrix);
  instance.geometry.computeBoundingBox();
  const bounds = instance.geometry.boundingBox!.clone().applyMatrix4(matrix);
  close(bounds.max.x, 100);
  close(bounds.min.x, 92);
  layer.dispose();
  mesh.geometry.dispose();
  (mesh.material as THREE.Material).dispose();
});

test("opt-in inspection reads actual baked geometry and instance buffers at cardinal headings", () => {
  const template = new THREE.Group();
  template.position.set(12, 0, 8);
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 4), new THREE.MeshBasicMaterial());
  mesh.position.set(3, 1, -5);
  template.add(mesh);
  const layer = new VehicleLayer(false, true);
  const templates = new Map([["ambulance", template]]);
  for (const angle of [0, 90, 180, 270]) {
    layer.update([{ id: "ambulance", type: "ambulance", x: 100, y: 200, z: 0,
      angle_deg: angle, speed_mps: 0, length_m: 8, width_m: 3 }], templates);
    const snapshot = layer.inspect()!;
    assert.equal(snapshot.types.ambulance.count, 1);
    const ambulance = snapshot.ambulances[0];
    close(ambulance.nose![0], 100);
    close(ambulance.nose![2], -200);
    close(ambulance.center![0], 100 - 4 * Math.sin(angle * Math.PI / 180));
    close(ambulance.center![2], -200 + 4 * Math.cos(angle * Math.PI / 180));
    close(ambulance.length!, 8);
    close(ambulance.width!, 3);
    close(ambulance.center![1], 1.12);
    assert.equal(ambulance.primitiveMatrices.length, 1);
  }
  // A changed render buffer must be observed without another input-pose update.
  const instance = layer.group.children[0] as THREE.InstancedMesh;
  const matrix = new THREE.Matrix4(); instance.getMatrixAt(0, matrix);
  matrix.elements[12] += 9; instance.setMatrixAt(0, matrix);
  close(layer.inspect()!.ambulances[0].nose![0], 109);
  layer.dispose(); mesh.geometry.dispose(); (mesh.material as THREE.Material).dispose();
});

test("ghost inspection counts only rendered ambulance instances and clears hidden layers", () => {
  const template = new THREE.Group();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 4), new THREE.MeshBasicMaterial());
  template.add(mesh);
  const layer = new VehicleLayer(true, true);
  const vehicle = { id: "ambulance", type: "ambulance", x: 0, y: 0, z: 0,
    angle_deg: 0, speed_mps: 0, length_m: 5 };
  layer.update([vehicle, { ...vehicle, id: "civilian", type: "car" }], new Map([["ambulance", template], ["car", template]]));
  assert.deepEqual(Object.keys(layer.inspect()!.types), ["ambulance"]);
  assert.equal(layer.inspect()!.types.ambulance.count, 1);
  layer.group.visible = false;
  assert.equal(layer.inspect()!.types.ambulance.count, 0);
  assert.equal(layer.inspect()!.ambulances.length, 0);
  layer.group.visible = true;
  layer.update([], new Map());
  assert.equal(layer.inspect()!.types.ambulance.count, 0);
  assert.equal(layer.inspect()!.ambulances.length, 0);
  layer.dispose(); mesh.geometry.dispose(); (mesh.material as THREE.Material).dispose();
});

test("inspection is disabled by default and does not traverse or allocate geometry bounds", () => {
  const layer = new VehicleLayer();
  layer.group.updateWorldMatrix = () => { throw new Error("Off-mode inspection traversed the scene"); };
  assert.equal(layer.inspect(), null);
  layer.dispose();
});


test("inspection reports incompatible primitive matrices instead of inventing a whole-body pose", () => {
  const template = new THREE.Group();
  const material = new THREE.MeshBasicMaterial();
  const first = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 4), material);
  const second = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), material);
  second.position.y = 2;
  template.add(first, second);
  const layer = new VehicleLayer(false, true);
  layer.update([{ id: "ambulance", type: "ambulance", x: 10, y: 20, z: 0,
    angle_deg: 0, speed_mps: 0, length_m: 8 }], new Map([["ambulance", template]]));
  assert.equal(layer.inspect()!.ambulances[0].consistentMatrices, true);
  const primitive = layer.group.children[1] as THREE.InstancedMesh;
  const matrix = new THREE.Matrix4(); primitive.getMatrixAt(0, matrix);
  matrix.elements[12] += 10; primitive.setMatrixAt(0, matrix);
  const snapshot = layer.inspect()!.ambulances[0];
  assert.equal(snapshot.consistentMatrices, false);
  assert.equal(snapshot.center, null);
  assert.equal(snapshot.nose, null);
  assert.equal(snapshot.length, null);
  assert.equal(snapshot.primitiveMatrices.length, 2);
  assert.ok(snapshot.bounds.max[0] > 15);
  layer.dispose(); first.geometry.dispose(); second.geometry.dispose(); material.dispose();
});
