import * as THREE from "three";
import type { Vehicle } from "./types.ts";
import { vehiclePose } from "./replay.ts";
interface Batch {
  capacity: number;
  meshes: THREE.InstancedMesh[];
  geometry: THREE.BufferGeometry[];
}
/** Original model primitives, baked once with their authored glTF transforms, instanced by type. */
export class VehicleLayer {
  readonly group = new THREE.Group();
  private batches = new Map<string, Batch>();
  private transform = new THREE.Object3D();
  constructor(private ghost = false) {}
  update(
    vehicles: Vehicle[],
    templates: Map<string, THREE.Group>,
    opacity = 0.38,
  ) {
    for (const batch of this.batches.values())
      for (const mesh of batch.meshes) mesh.count = 0;
    const types = new Map<string, Vehicle[]>();
    for (const vehicle of vehicles) {
      if (this.ghost && vehicle.type !== "ambulance") continue;
      const list = types.get(vehicle.type) ?? [];
      list.push(vehicle);
      types.set(vehicle.type, list);
    }
    for (const [type, rows] of types) {
      const template = templates.get(type);
      if (!template) continue;
      let batch = this.batches.get(type);
      if (!batch || batch.capacity < rows.length) {
        if (batch) this.remove(batch);
        batch = this.create(
          template,
          2 ** Math.ceil(Math.log2(Math.max(1, rows.length))),
        );
        this.batches.set(type, batch);
      }
      for (let i = 0; i < rows.length; i++) {
        const [x, y, z, angle] = vehiclePose(rows[i]);
        this.transform.position.set(x, y + 0.12, z);
        this.transform.rotation.set(0, angle, 0);
        this.transform.updateMatrix();
        for (const mesh of batch.meshes)
          mesh.setMatrixAt(i, this.transform.matrix);
      }
      for (const mesh of batch.meshes) {
        mesh.count = rows.length;
        mesh.instanceMatrix.needsUpdate = true;
        if (this.ghost) (mesh.material as THREE.Material).opacity = opacity;
      }
    }
  }
  private create(template: THREE.Group, capacity: number): Batch {
    const batch: Batch = { capacity, meshes: [], geometry: [] };
    template.updateMatrixWorld(true);
    template.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      const geometry = child.geometry.clone().applyMatrix4(child.matrixWorld);
      const material = this.ghost
        ? new THREE.MeshBasicMaterial({
            color: 0x87d7ff,
            transparent: true,
            opacity: 0.38,
            depthWrite: false,
          })
        : child.material;
      const mesh = new THREE.InstancedMesh(geometry, material, capacity);
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.frustumCulled = false;
      mesh.count = 0;
      mesh.renderOrder = this.ghost ? 3 : 0;
      this.group.add(mesh);
      batch.meshes.push(mesh);
      batch.geometry.push(geometry);
    });
    return batch;
  }
  private remove(batch: Batch) {
    for (const mesh of batch.meshes) {
      this.group.remove(mesh);
      mesh.dispose();
      if (this.ghost) (mesh.material as THREE.Material).dispose();
    }
    for (const g of batch.geometry) g.dispose();
  }
  dispose() {
    for (const batch of this.batches.values()) this.remove(batch);
    this.batches.clear();
  }
}
