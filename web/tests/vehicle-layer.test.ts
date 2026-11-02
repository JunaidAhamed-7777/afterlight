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
