import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { BuildingCutaway } from "../src/BuildingCutaway.ts";

// CPU geometry/material fixtures only. Actual shader rendering and appearance require Omen Chrome.
function fixture() {
  const scene = new THREE.Scene();
  const root = new THREE.Group();
  root.position.set(10, -3, -7.5);
  scene.add(root);
  const shared = new THREE.MeshStandardMaterial({ color: 0x559977 });
  const building = (id: string, x: number, z: number) => {
    const node = new THREE.Group();
    node.name = `AL_BUILDING_${id}`;
    node.userData = { building_id: id, occluder: true };
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(4, 8, 4), shared);
    mesh.position.set(x, 4, z); node.add(mesh); root.add(node);
    return node;
  };
  const first = building("A", 0, 5), second = building("B", 35, 5);
  const ground = new THREE.Mesh(new THREE.BoxGeometry(100, 0.2, 100), shared);
  ground.name = "AL_GROUND"; ground.userData.occluder = false; root.add(ground);
  scene.updateMatrixWorld(true);
  return { scene, root, first, second, ground, shared };
}

test("building batches preserve world bounds once and exclude shared-color ground", () => {
  const f = fixture();
  const expected = new THREE.Box3().setFromObject(f.first).union(new THREE.Box3().setFromObject(f.second));
  const originalGround = f.ground.geometry.getAttribute("position").array.slice();
  const cutaway = new BuildingCutaway(); cutaway.install(f.root);
  assert.equal(cutaway.count, 2);
  assert.equal(cutaway.batches.children.length, 1, "shared building material should batch once");
  const actual = new THREE.Box3().setFromObject(cutaway.batches);
  assert.ok(actual.min.distanceTo(expected.min) < 1e-5);
  assert.ok(actual.max.distanceTo(expected.max) < 1e-5);
  assert.equal(f.first.visible, false); assert.equal(f.second.visible, false);
  assert.equal(f.ground.visible, true); assert.equal(f.ground.material, f.shared);
  assert.deepEqual(f.ground.geometry.getAttribute("position").array, originalGround);
  assert.equal(f.shared.opacity, 1); assert.equal(f.shared.transparent, false);
  cutaway.dispose();
});

test("foreground building fades independently and restores without altering shared materials", () => {
  const f = fixture(); const cutaway = new BuildingCutaway(); cutaway.install(f.root);
  const camera = new THREE.PerspectiveCamera();
  const origin = f.root.position;
  const focus = new THREE.Vector3(0, 2, 0).add(origin);
  camera.position.copy(new THREE.Vector3(0, 4, 20).add(origin));
  camera.lookAt(focus); camera.updateMatrixWorld(true);
  assert.equal(cutaway.update(true, focus, camera), 1);
  const batch = cutaway.batches.children[0] as THREE.Mesh;
  const material = batch.material as THREE.Material;
  // Inspect only the CPU uniform wiring; this is not shader compilation evidence.
  const shader: any = { uniforms: {}, vertexShader: "#include <begin_vertex>", fragmentShader: "#include <clipping_planes_fragment>" };
  material.onBeforeCompile(shader, {} as THREE.WebGLRenderer);
  const texture = shader.uniforms.afterlightBuildingOpacity.value as THREE.DataTexture;
  const bytes = texture.image.data;
  assert.equal(bytes[0], 36); assert.equal(bytes[4], 255);
  assert.equal(f.shared.opacity, 1); assert.equal(f.ground.visible, true);
  assert.equal(cutaway.update(false, focus, camera), 0);
  assert.equal(bytes[0], 255); assert.equal(bytes[4], 255);
  assert.equal(cutaway.update(true, new THREE.Vector3(0, 2, 40).add(origin), camera), 0, "behind-camera buildings must not fade");
  cutaway.dispose(); assert.equal(cutaway.batches.parent, null);
  assert.equal(cutaway.batches.children.length, 0);
});

test("missing and duplicate building identities fail instead of fading the whole city", () => {
  assert.throws(() => new BuildingCutaway().install(new THREE.Group()), /no addressable/);
  const f = fixture(); f.second.userData.building_id = "A";
  assert.throws(() => new BuildingCutaway().install(f.root), /repeats building ID/);
  assert.equal(f.first.visible, true); assert.equal(f.ground.visible, true);
});
