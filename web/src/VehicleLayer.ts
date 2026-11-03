import * as THREE from "three";
import type { Vehicle } from "./types.ts";
import { vehiclePose } from "./replay.ts";
interface Batch {
  capacity: number;
  meshes: THREE.InstancedMesh[];
  geometry: THREE.BufferGeometry[];
  length: number;
  width: number;
}
/** Original model primitives, baked once with their authored glTF transforms, instanced by type. */
export class VehicleLayer {
  readonly group = new THREE.Group();
  private batches = new Map<string, Batch>();
  private transform = new THREE.Object3D();
  private ghost: boolean;
  private readonly inspectionEnabled: boolean;
  constructor(ghost = false, inspectionEnabled = false) {
    this.ghost = ghost;
    this.inspectionEnabled = inspectionEnabled;
  }
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
        this.transform.scale.set(
          rows[i].width_m ? rows[i].width_m! / batch.width : 1,
          1,
          rows[i].length_m / batch.length,
        );
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
  /** Opt-in QA snapshot of render buffers, never input poses or simulation state. */
  inspect() {
    if (!this.inspectionEnabled) return null;
    this.group.updateWorldMatrix(true, true);
    const types: Record<string, { count: number; primitiveCounts: number[] }> = {};
    const ambulances: Array<{
      instance: number; consistentMatrices: boolean; center: number[] | null; nose: number[] | null; rear: number[] | null;
      length: number | null; width: number | null; bounds: { min: number[]; max: number[] };
      primitiveMatrices: number[][];
    }> = [];
    let layerVisible = true;
    for (let node: THREE.Object3D | null = this.group; node; node = node.parent)
      if (!node.visible) layerVisible = false;
    for (const [type, batch] of this.batches) {
      const visible = batch.meshes.filter(mesh => layerVisible && mesh.visible);
      const primitiveCounts = batch.meshes.map(mesh => layerVisible && mesh.visible ? mesh.count : 0);
      const count = Math.max(0, ...primitiveCounts);
      types[type] = { count, primitiveCounts };
      if (type !== "ambulance") continue;
      for (let i = 0; i < count; i++) {
        const localBounds = new THREE.Box3();
        const worldBounds = new THREE.Box3();
        const primitiveMatrices: number[][] = [];
        let referenceMatrix: THREE.Matrix4 | null = null;
        let consistentMatrices = true;
        for (const mesh of visible) {
          if (i >= mesh.count) continue;
          if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
          const baked = mesh.geometry.boundingBox!;
          const matrix = new THREE.Matrix4();
          mesh.getMatrixAt(i, matrix);
          matrix.premultiply(mesh.matrixWorld);
          if (referenceMatrix && !referenceMatrix.equals(matrix)) consistentMatrices = false;
          referenceMatrix ??= matrix;
          primitiveMatrices.push(matrix.toArray());
          localBounds.union(baked);
          worldBounds.union(baked.clone().applyMatrix4(matrix));
        }
        if (!referenceMatrix || localBounds.isEmpty()) continue;
        if (!consistentMatrices) {
          ambulances.push({ instance: i, consistentMatrices: false, center: null, nose: null, rear: null,
            length: null, width: null, bounds: { min: worldBounds.min.toArray(), max: worldBounds.max.toArray() }, primitiveMatrices });
          continue;
        }
        const localCenter = localBounds.getCenter(new THREE.Vector3());
        const center = localCenter.clone().applyMatrix4(referenceMatrix);
        const nose = new THREE.Vector3(localCenter.x, localCenter.y, localBounds.min.z).applyMatrix4(referenceMatrix);
        const rear = new THREE.Vector3(localCenter.x, localCenter.y, localBounds.max.z).applyMatrix4(referenceMatrix);
        const left = new THREE.Vector3(localBounds.min.x, localCenter.y, localCenter.z).applyMatrix4(referenceMatrix);
        const right = new THREE.Vector3(localBounds.max.x, localCenter.y, localCenter.z).applyMatrix4(referenceMatrix);
        ambulances.push({ instance: i, consistentMatrices: true, center: center.toArray(), nose: nose.toArray(), rear: rear.toArray(),
          length: nose.distanceTo(rear), width: left.distanceTo(right),
          bounds: { min: worldBounds.min.toArray(), max: worldBounds.max.toArray() }, primitiveMatrices });
      }
    }
    return { source: "InstancedMesh matrices and baked geometry bounds", types, ambulances };
  }
  private create(template: THREE.Group, capacity: number): Batch {
    template.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(template);
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    if (size.z <= 0 || size.x <= 0)
      throw new Error("Vehicle asset has no measurable footprint.");
    const batch: Batch = {
      capacity,
      meshes: [],
      geometry: [],
      length: size.z,
      width: size.x,
    };
    template.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      const geometry = child.geometry
        .clone()
        .applyMatrix4(child.matrixWorld)
        .translate(-center.x, 0, -center.z);
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
