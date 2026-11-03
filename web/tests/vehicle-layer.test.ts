import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { readFileSync } from "node:fs";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { AUTHORED_ROAD_SURFACE_Y, VehicleLayer } from "../src/VehicleLayer.ts";
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
    close(ambulance.center![1], 1.18);
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

test("selected civilian inspection follows actual buffers through reorder, pool growth and departure", () => {
  const template = new THREE.Group();
  const geometry = new THREE.BoxGeometry(2, 2, 4);
  const material = new THREE.MeshBasicMaterial();
  template.add(new THREE.Mesh(geometry, material));
  const layer = new VehicleLayer(false, true, ["chosen"]);
  const templates = new Map([["car", template]]);
  const row = (id: string, x: number) => ({ id, type: "car", x, y: 20, z: 0,
    angle_deg: 90, speed_mps: 0, length_m: 4.4, width_m: 1.8 });
  layer.update([row("other", 10), row("chosen", 100)], templates);
  let selected = layer.inspect()!.selectedVehicles;
  assert.deepEqual(selected.map(v => v.id), ["chosen"]);
  assert.equal(selected[0].instance, 1);
  close(selected[0].nose![0], 100);
  const instance = layer.group.children[0] as THREE.InstancedMesh;
  const matrix = new THREE.Matrix4(); instance.getMatrixAt(1, matrix);
  matrix.elements[12] += 9; instance.setMatrixAt(1, matrix);
  close(layer.inspect()!.selectedVehicles[0].nose![0], 109);
  layer.update([row("chosen", 50), ...Array.from({ length: 10 }, (_, i) => row(`new-${i}`, i))], templates);
  selected = layer.inspect()!.selectedVehicles;
  assert.equal(selected[0].instance, 0);
  close(selected[0].nose![0], 50);
  close(selected[0].bounds.min[1], AUTHORED_ROAD_SURFACE_Y);
  assert.deepEqual(layer.inspect()!.ambulances, []);
  layer.update([row("other", 10)], templates);
  assert.deepEqual(layer.inspect()!.selectedVehicles, []);
  layer.dispose(); geometry.dispose(); material.dispose();
});

test("disabled selected inspection performs no vehicle-ID lookup or scene traversal", () => {
  const template = new THREE.Group();
  const geometry = new THREE.BoxGeometry(2, 2, 4);
  const material = new THREE.MeshBasicMaterial();
  template.add(new THREE.Mesh(geometry, material));
  const layer = new VehicleLayer(false, false, ["chosen"]);
  const vehicle = { get id(): string { throw new Error("Disabled inspector read an ID"); },
    type: "car", x: 10, y: 20, z: 0, angle_deg: 90, speed_mps: 0, length_m: 4.4 };
  layer.update([vehicle], new Map([["car", template]]));
  layer.group.updateWorldMatrix = () => { throw new Error("Disabled inspector traversed scene"); };
  assert.equal(layer.inspect(), null);
  layer.dispose(); geometry.dispose(); material.dispose();
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


test("every vehicle type and ghost contacts authored road top without changing geometry or XZ nose", () => {
  for (const type of ["ambulance", "car", "truck", "bike"]) {
    for (const ghost of type === "ambulance" ? [false, true] : [false]) {
      const template = new THREE.Group();
      template.position.set(12, 3.25, -8);
      const geometry = new THREE.BoxGeometry(2, 2, 4);
      const material = new THREE.MeshBasicMaterial();
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(2, -0.61, 1);
      template.add(mesh);
      const originalVertices = Array.from(geometry.attributes.position.array);
      const layer = new VehicleLayer(ghost);
      for (const elevation of [0, 3.75]) {
        layer.update([{ id: type === "ambulance" ? "ambulance" : "civilian", type,
          x: 100, y: 200, z: elevation, angle_deg: 90, speed_mps: 0, length_m: 8, width_m: 3 }],
          new Map([[type, template]]));
        const instance = layer.group.children[0] as THREE.InstancedMesh;
        const matrix = new THREE.Matrix4(); instance.getMatrixAt(0, matrix);
        const rendered = instance.geometry.boundingBox!.clone().applyMatrix4(matrix);
        close(rendered.min.y, elevation + AUTHORED_ROAD_SURFACE_Y);
        close(rendered.max.y - rendered.min.y, 2);
        close(rendered.max.x, 100);
        close(rendered.min.x, 92);
        close((rendered.min.z + rendered.max.z) / 2, -200);
      }
      assert.deepEqual(template.position.toArray(), [12, 3.25, -8]);
      assert.deepEqual(mesh.position.toArray(), [2, -0.61, 1]);
      assert.deepEqual(Array.from(geometry.attributes.position.array), originalVertices);
      layer.dispose(); geometry.dispose(); material.dispose();
    }
  }
});

async function actualTemplate(type: string): Promise<THREE.Group> {
  const bytes = readFileSync(new URL(`../../assets/exports/${type}.glb`, import.meta.url));
  return (await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), "")).scene;
}
function civilian(id: string, type = "car") {
  return { id, type, x: 12, y: 30, z: 0, angle_deg: 90, speed_mps: 4, length_m: type === "truck" ? 6 : type === "bike" ? 1.8 : 4.5 };
}
function painted(layer: VehicleLayer) {
  return (layer.group.children as THREE.InstancedMesh[]).filter((mesh) => mesh.instanceColor !== null);
}
function instanceColor(mesh: THREE.InstancedMesh, index: number) {
  const color = new THREE.Color();mesh.getColorAt(index,color);return color.toArray();
}

test("actual civilian GLBs vary only their paint without adding batches or altering source materials", async () => {
  const expectedPaint = { car: ["bluegrey"], truck: ["cream", "porcelain"], bike: ["terracotta"] };
  for (const type of ["car", "truck", "bike"] as const) {
    const template = await actualTemplate(type);
    const originals: THREE.Material[] = [];
    const colors: number[][] = [];
    template.traverse((node) => {
      if (node instanceof THREE.Mesh) {
        const material = node.material as THREE.MeshStandardMaterial;
        originals.push(material);colors.push(material.color.toArray());
      }
    });
    const layer = new VehicleLayer();
    layer.update(Array.from({ length: 24 }, (_,i) => civilian(`civilian-${i}`,type)),new Map([[type,template]]));
    assert.equal(layer.group.children.length,originals.length,"Paint must retain one batch per original primitive");
    assert.equal(painted(layer).length,expectedPaint[type].length);
    for (const [index,child] of layer.group.children.entries()) {
      const instance = child as THREE.InstancedMesh;
      const original = originals[index] as THREE.MeshStandardMaterial;
      assert.deepEqual(original.color.toArray(),colors[index],"Shared GLB material was modified");
      if ((expectedPaint[type] as readonly string[]).includes(original.name)) {
        assert.notEqual(instance.material,original);
        assert.deepEqual((instance.material as THREE.MeshStandardMaterial).color.toArray(),[1,1,1]);
        const choices = new Set(Array.from({length:24},(_,i) => instanceColor(instance,i).map(n => n.toFixed(5)).join(",")));
        assert.equal(choices.size,8,"A real traffic population should use the complete stable palette");
      } else {
        assert.equal(instance.material,original,"Glass, tyres, lamps and metal must retain original materials");
        assert.equal(instance.instanceColor,null);
      }
    }
    layer.dispose();
  }
});

test("paint follows vehicle ID through reordered frames, pool growth, despawn and independent worlds", async () => {
  const template=await actualTemplate("car");
  const templates=new Map([["car",template]]);
  const active=new VehicleLayer();const baseline=new VehicleLayer();
  const first=[civilian("civilian-7"),civilian("civilian-9")];
  active.update(first,templates);
  const original=new Map(first.map((v,i) => [v.id,instanceColor(painted(active)[0],i)]));
  const second=[first[1],...Array.from({length:12},(_,i) => civilian(`new-${i}`)),first[0]];
  active.update(second,templates);baseline.update([...second].reverse(),templates);
  for (const [i,v] of second.entries()) {
    const actual=instanceColor(painted(active)[0],i);
    const other=instanceColor(painted(baseline)[0],second.length-1-i);
    actual.forEach((n,j) => close(n,other[j]));
    original.get(v.id)?.forEach((n,j) => close(actual[j],n));
  }
  active.update([],templates);active.update([first[0]],templates);
  instanceColor(painted(active)[0],0).forEach((n,j) => close(n,original.get(first[0].id)![j]));
  active.dispose();baseline.dispose();
});

test("ambulance and ghost never receive civilian paint and owned paint materials are released", async () => {
  const ambulance=await actualTemplate("ambulance");const car=await actualTemplate("car");
  const templates=new Map([["ambulance",ambulance],["car",car]]);
  const active=new VehicleLayer();const ghost=new VehicleLayer(true);
  active.update([civilian("ambulance","ambulance")],templates);
  assert.equal(painted(active).length,0);
  ghost.update([civilian("ambulance","ambulance"),civilian("ignored")],templates,.27);
  assert.equal(painted(ghost).length,0);
  for (const child of ghost.group.children as THREE.InstancedMesh[]) {
    const material=child.material as THREE.MeshBasicMaterial;
    assert.equal(material.color.getHex(),0x87d7ff);
    assert.equal(material.opacity,.27);
    assert.equal(material.depthWrite,false);
  }
  active.update([civilian("civilian-1")],templates);
  const paintMaterial=painted(active)[0].material as THREE.Material;
  let released=0;paintMaterial.addEventListener("dispose",() => released++);
  let originalReleased=0;
  car.traverse(node => { if(node instanceof THREE.Mesh)(node.material as THREE.Material).addEventListener("dispose",() => originalReleased++); });
  active.update(Array.from({length:5},(_,i) => civilian(`civilian-${i}`)),templates);
  assert.equal(released,1,"Growing the pool must dispose its previous paint material");
  active.dispose();ghost.dispose();
  assert.equal(released,1);
  assert.equal(originalReleased,0,"Disposing instance pools must preserve shared GLB materials");
});

test("actual roof beacons alternate without changing the source, vehicle pose or ghost", async () => {
  const template = await actualTemplate("ambulance");
  const templates = new Map([["ambulance", template]]);
  const originals: THREE.MeshStandardMaterial[] = [];
  template.traverse(node => {
    if (node instanceof THREE.Mesh) originals.push(node.material as THREE.MeshStandardMaterial);
  });
  const sourceColors = originals.map(material => material.color.toArray());
  const active = new VehicleLayer(false, true), ghost = new VehicleLayer(true);
  const vehicle = civilian("ambulance", "ambulance");
  active.update([vehicle], templates);
  ghost.update([vehicle], templates);
  const meshes = active.group.children as THREE.InstancedMesh[];
  assert.equal(meshes.length, originals.length, "Roof lights reuse original model primitives");
  const lights = meshes.filter(mesh => (mesh.material as THREE.Material).name === "AFTERLIGHT_EMERGENCY_BEACON");
  assert.equal(lights.length, 1, "The authored roof bar is the only animated material");
  const material = lights[0].material as THREE.MeshStandardMaterial;
  const before = active.inspect()!.ambulances[0];
  assert.equal(active.updateBeacons(0, true), true);
  assert.equal(material.color.getHex(), 0x2288ff);
  assert.equal(active.updateBeacons(.2, true), false);
  assert.equal(active.updateBeacons(.41, true), true);
  assert.equal(material.color.getHex(), 0xff304d);
  assert.equal(material.emissive.getHex(), 0xff304d);
  assert.equal(active.updateBeacons(.81, true), true);
  assert.equal(material.color.getHex(), 0x2288ff);
  active.updateBeacons(1.21, true);
  assert.equal(active.updateBeacons(1.21, false), true, "Paused or reduced-motion playback uses steady blue");
  assert.equal(active.updateBeacons(9.21, false), false);
  assert.equal(material.color.getHex(), 0x2288ff);
  assert.deepEqual(active.inspect()!.ambulances[0], before);
  for (const [index, mesh] of meshes.entries()) {
    assert.deepEqual(originals[index].color.toArray(), sourceColors[index]);
    if (mesh !== lights[0]) assert.equal(mesh.material, originals[index]);
  }
  assert.equal(ghost.updateBeacons(.41, true), false);
  for (const mesh of ghost.group.children as THREE.InstancedMesh[])
    assert.equal((mesh.material as THREE.MeshBasicMaterial).color.getHex(), 0x87d7ff);
  active.update([], templates);
  assert.equal(active.updateBeacons(.41, true), false, "An absent ambulance must not request animation frames");
  let disposed = 0;
  material.addEventListener("dispose", () => disposed++);
  active.dispose(); ghost.dispose();
  assert.equal(disposed, 1);
});
