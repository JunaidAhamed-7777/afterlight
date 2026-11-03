import * as THREE from "three";
import type { Vehicle } from "./types.ts";
import { vehiclePose } from "./replay.ts";
// assets/src/generate_city.py: road box center Z=.12 m, thickness=.12 m.
// Blender +Z maps to render +Y; keep canonical road/vehicle XY and GLBs untouched.
export const AUTHORED_ROAD_SURFACE_Y = 0.18;
// Stable vehicle identity owns paint, so scrubbing, world switches and instance
// pool growth never recolor a vehicle. THREE.Color converts these sRGB swatches.
const CIVILIAN_PAINT = [
  0xf2efe3, 0x337ab0, 0xd26450, 0x4f9a80, 0xd9b04f, 0x4b5d6a, 0x8a78a3,
  0x2e6d83,
].map((hex) => new THREE.Color(hex));
const PAINT_MATERIAL_NAMES: Record<string, readonly string[]> = {
  car: ["bluegrey"],
  truck: ["cream", "porcelain"],
  bike: ["terracotta"],
};
function civilianPaint(id: string): THREE.Color {
  let hash = 0x811c9dc5;
  for (let i = 0; i < id.length; i++)
    hash = Math.imul(hash ^ id.charCodeAt(i), 0x01000193);
  return CIVILIAN_PAINT[(hash >>> 0) % CIVILIAN_PAINT.length];
}
interface Batch {
  capacity: number;
  meshes: THREE.InstancedMesh[];
  geometry: THREE.BufferGeometry[];
  paintedMeshes: THREE.InstancedMesh[];
  ownedMaterials: THREE.Material[];
  beaconMaterials: THREE.MeshStandardMaterial[];
  beaconColor: number | null;
  length: number;
  width: number;
  minY: number;
}
interface InspectedInstance {
  instance: number;
  consistentMatrices: boolean;
  center: number[] | null;
  nose: number[] | null;
  rear: number[] | null;
  length: number | null;
  width: number | null;
  bounds: { min: number[]; max: number[] };
  primitiveMatrices: number[][];
}
/** Original model primitives, baked once with their authored glTF transforms, instanced by type. */
export class VehicleLayer {
  readonly group = new THREE.Group();
  private batches = new Map<string, Batch>();
  private transform = new THREE.Object3D();
  private ghost: boolean;
  private readonly inspectionEnabled: boolean;
  private readonly inspectionIds: Set<string> | null;
  private readonly inspectionSelection: Map<string, { type: string; instance: number }> | null;
  constructor(ghost = false, inspectionEnabled = false, inspectionIds: readonly string[] = []) {
    this.ghost = ghost;
    this.inspectionEnabled = inspectionEnabled;
    this.inspectionIds = inspectionEnabled && inspectionIds.length ? new Set(inspectionIds.slice(0, 16)) : null;
    this.inspectionSelection = this.inspectionIds ? new Map() : null;
  }
  update(
    vehicles: Vehicle[],
    templates: Map<string, THREE.Group>,
    opacity = 0.38,
  ) {
    this.inspectionSelection?.clear();
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
          type,
        );
        this.batches.set(type, batch);
      }
      if (this.inspectionSelection && this.inspectionIds)
        for (const id of this.inspectionIds) {
          const instance = rows.findIndex(row => row.id === id);
          if (instance >= 0) this.inspectionSelection.set(id, { type, instance });
        }
      for (let i = 0; i < rows.length; i++) {
        const [x, y, z, angle] = vehiclePose(rows[i]);
        this.transform.position.set(
          x,
          y + AUTHORED_ROAD_SURFACE_Y - batch.minY,
          z,
        );
        this.transform.rotation.set(0, angle, 0);
        this.transform.scale.set(
          rows[i].width_m ? rows[i].width_m! / batch.width : 1,
          1,
          rows[i].length_m / batch.length,
        );
        this.transform.updateMatrix();
        for (const mesh of batch.meshes)
          mesh.setMatrixAt(i, this.transform.matrix);
        if (batch.paintedMeshes.length) {
          const color = civilianPaint(rows[i].id);
          for (const mesh of batch.paintedMeshes) mesh.setColorAt(i, color);
        }
      }
      for (const mesh of batch.meshes) {
        mesh.count = rows.length;
        mesh.instanceMatrix.needsUpdate = true;
        if (this.ghost) (mesh.material as THREE.Material).opacity = opacity;
      }
      for (const mesh of batch.paintedMeshes)
        mesh.instanceColor!.needsUpdate = true;
    }
  }
  /** Presentation-only roof lights; wall time keeps playback speed independent of flashing. */
  updateBeacons(wallSeconds: number, flashing: boolean): boolean {
    const batch = this.batches.get("ambulance");
    if (!batch?.beaconMaterials.length || !batch.meshes.some(mesh => mesh.count > 0))
      return false;
    const color = flashing && Math.floor(wallSeconds * 2.5) % 2 ? 0xff304d : 0x2288ff;
    if (batch.beaconColor === color) return false;
    batch.beaconColor = color;
    for (const material of batch.beaconMaterials) {
      material.color.setHex(color);
      material.emissive.setHex(color);
    }
    return true;
  }
  /** Opt-in QA snapshot of render buffers, never input poses or simulation state. */
  inspect() {
    if (!this.inspectionEnabled) return null;
    this.group.updateWorldMatrix(true, true);
    const types: Record<string, { count: number; primitiveCounts: number[] }> =
      {};
    const ambulances: InspectedInstance[] = [];
    const selectedVehicles: Array<InspectedInstance & { id: string; type: string }> = [];
    let layerVisible = true;
    for (let node: THREE.Object3D | null = this.group; node; node = node.parent)
      if (!node.visible) layerVisible = false;
    for (const [type, batch] of this.batches) {
      const visible = batch.meshes.filter(
        (mesh) => layerVisible && mesh.visible,
      );
      const primitiveCounts = batch.meshes.map((mesh) =>
        layerVisible && mesh.visible ? mesh.count : 0,
      );
      const count = Math.max(0, ...primitiveCounts);
      types[type] = { count, primitiveCounts };
      const selected = new Map<number, string>();
      if (this.inspectionSelection)
        for (const [id, row] of this.inspectionSelection)
          if (row.type === type && row.instance < count) selected.set(row.instance, id);
      if (type !== "ambulance" && !selected.size) continue;
      const instances = type === "ambulance" ? Array.from({ length: count }, (_, i) => i) : selected.keys();
      for (const i of instances) {
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
          if (referenceMatrix && !referenceMatrix.equals(matrix))
            consistentMatrices = false;
          referenceMatrix ??= matrix;
          primitiveMatrices.push(matrix.toArray());
          localBounds.union(baked);
          worldBounds.union(baked.clone().applyMatrix4(matrix));
        }
        if (!referenceMatrix || localBounds.isEmpty()) continue;
        if (!consistentMatrices) {
          const inspected: InspectedInstance = {
            instance: i,
            consistentMatrices: false,
            center: null,
            nose: null,
            rear: null,
            length: null,
            width: null,
            bounds: {
              min: worldBounds.min.toArray(),
              max: worldBounds.max.toArray(),
            },
            primitiveMatrices,
          };
          if (type === "ambulance") ambulances.push(inspected);
          if (selected.has(i)) selectedVehicles.push({ ...inspected, id: selected.get(i)!, type });
          continue;
        }
        const localCenter = localBounds.getCenter(new THREE.Vector3());
        const center = localCenter.clone().applyMatrix4(referenceMatrix);
        const nose = new THREE.Vector3(
          localCenter.x,
          localCenter.y,
          localBounds.min.z,
        ).applyMatrix4(referenceMatrix);
        const rear = new THREE.Vector3(
          localCenter.x,
          localCenter.y,
          localBounds.max.z,
        ).applyMatrix4(referenceMatrix);
        const left = new THREE.Vector3(
          localBounds.min.x,
          localCenter.y,
          localCenter.z,
        ).applyMatrix4(referenceMatrix);
        const right = new THREE.Vector3(
          localBounds.max.x,
          localCenter.y,
          localCenter.z,
        ).applyMatrix4(referenceMatrix);
        const inspected: InspectedInstance = {
          instance: i,
          consistentMatrices: true,
          center: center.toArray(),
          nose: nose.toArray(),
          rear: rear.toArray(),
          length: nose.distanceTo(rear),
          width: left.distanceTo(right),
          bounds: {
            min: worldBounds.min.toArray(),
            max: worldBounds.max.toArray(),
          },
          primitiveMatrices,
        };
        if (type === "ambulance") ambulances.push(inspected);
        if (selected.has(i)) selectedVehicles.push({ ...inspected, id: selected.get(i)!, type });
      }
    }
    return {
      source: "InstancedMesh matrices and baked geometry bounds",
      types,
      ambulances,
      selectedVehicles,
      beaconMaterials: (this.batches.get("ambulance")?.beaconMaterials ?? []).map((material) => ({
        name: material.name,
        color: `#${material.color.getHexString()}`,
        emissive: `#${material.emissive.getHexString()}`,
        emissiveIntensity: material.emissiveIntensity,
        toneMapped: material.toneMapped,
      })),
    };
  }
  private create(template: THREE.Group, capacity: number, type: string): Batch {
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
      paintedMeshes: [],
      ownedMaterials: [],
      beaconMaterials: [],
      beaconColor: null,
      length: size.z,
      width: size.x,
      minY: Infinity,
    };
    template.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      const geometry = child.geometry
        .clone()
        .applyMatrix4(child.matrixWorld)
        .translate(-center.x, 0, -center.z);
      geometry.computeBoundingBox();
      batch.minY = Math.min(batch.minY, geometry.boundingBox!.min.y);
      let material = this.ghost
        ? new THREE.MeshBasicMaterial({
            color: 0x87d7ff,
            transparent: true,
            opacity: 0.38,
            depthWrite: false,
          })
        : child.material;
      let paint = false;
      if (this.ghost) batch.ownedMaterials.push(material as THREE.Material);
      else if (
        type === "ambulance" &&
        material instanceof THREE.MeshStandardMaterial &&
        material.name === "beacon_cyan"
      ) {
        const beacon = material.clone();
        beacon.name = "AFTERLIGHT_EMERGENCY_BEACON";
        beacon.toneMapped = false;
        beacon.emissiveIntensity = 3;
        material = beacon;
        batch.beaconMaterials.push(beacon);
        batch.ownedMaterials.push(beacon);
      } else if (
        !Array.isArray(material) &&
        PAINT_MATERIAL_NAMES[type]?.includes(material.name) &&
        (material instanceof THREE.MeshStandardMaterial ||
          material instanceof THREE.MeshBasicMaterial)
      ) {
        material = material.clone();
        (
          material as THREE.MeshStandardMaterial | THREE.MeshBasicMaterial
        ).color.setHex(0xffffff);
        material.name = `AFTERLIGHT_CIVILIAN_PAINT_${type}_${child.material instanceof THREE.Material ? child.material.name : "body"}`;
        batch.ownedMaterials.push(material);
        paint = true;
      }
      const mesh = new THREE.InstancedMesh(geometry, material, capacity);
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.frustumCulled = false;
      mesh.receiveShadow = !this.ghost;
      mesh.count = 0;
      mesh.renderOrder = this.ghost ? 3 : 0;
      if (paint) {
        mesh.instanceColor = new THREE.InstancedBufferAttribute(
          new Float32Array(capacity * 3).fill(1),
          3,
        );
        mesh.instanceColor.setUsage(THREE.DynamicDrawUsage);
        batch.paintedMeshes.push(mesh);
      }
      this.group.add(mesh);
      batch.meshes.push(mesh);
      batch.geometry.push(geometry);
    });
    if (!Number.isFinite(batch.minY)) {
      this.remove(batch);
      throw new Error("Vehicle asset has no measurable ground contact.");
    }
    return batch;
  }
  private remove(batch: Batch) {
    for (const mesh of batch.meshes) {
      this.group.remove(mesh);
      mesh.dispose();
    }
    for (const material of batch.ownedMaterials) material.dispose();
    for (const g of batch.geometry) g.dispose();
  }
  dispose() {
    for (const batch of this.batches.values()) this.remove(batch);
    this.batches.clear();
  }
}
