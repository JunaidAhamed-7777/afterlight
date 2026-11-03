import * as THREE from "three";
import type { City } from "./types.ts";
export type MapPickMode = "pickup" | "hospital" | null;
interface Anchor { id: string; label: string; position: THREE.Vector3 }
/** Canonical anchors only. This render-only layer never reads vehicles or the ghost. */
export class MapSelectionLayer {
  readonly mesh = new THREE.InstancedMesh(
    new THREE.SphereGeometry(1, 10, 6),
    new THREE.MeshBasicMaterial({ color: 0xffb85c, depthTest: false, depthWrite: false }),
    100,
  );
  private anchors: Anchor[] = [];
  private city: City | null = null;
  private mode: MapPickMode = null;
  private raycaster = new THREE.Raycaster();
  constructor() {
    this.mesh.count = 0;
    this.mesh.visible = false;
    this.mesh.renderOrder = 10;
    this.mesh.name = "Canonical map selection anchors";
  }
  setAnchors(city: City | null, mode: MapPickMode) {
    if (city === this.city && mode === this.mode) return;
    const rows = !city || !mode ? [] : mode === "pickup"
      ? city.pickups.map(p => ({ id: p.id, label: `${p.id} · ${p.road_id}`, point: p.position }))
      : city.hospitals.map(h => ({ id: h.id, label: h.name ?? h.id, point: h.driveway_anchor }));
    if (rows.length > 100) throw new Error("Canonical anchor count exceeds the selection layer capacity.");
    const anchors = rows.map(row => ({ id: row.id, label: row.label,
      position: new THREE.Vector3(row.point[0], (row.point[2] ?? 0) + 2, -row.point[1]) }));
    this.anchors = anchors;
    this.city = city;
    this.mode = mode;
    this.mesh.count = this.anchors.length;
    this.mesh.visible = this.anchors.length > 0;
    this.mesh.material.color.set(mode === "hospital" ? 0x78d9cb : 0xffb85c);
  }
  update(camera: THREE.Camera, viewportHeight: number) {
    if (!this.mesh.visible) return;
    const matrix = new THREE.Matrix4();
    const rotation = new THREE.Quaternion();
    const scale = new THREE.Vector3();
    camera.updateMatrixWorld(true);
    for (let index = 0; index < this.anchors.length; index++) {
      const position = this.anchors[index].position;
      let visibleHeight = 1;
      if (camera instanceof THREE.PerspectiveCamera) {
        const depth = -position.clone().applyMatrix4(camera.matrixWorldInverse).z;
        visibleHeight = 2 * Math.max(camera.near, depth) * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / camera.zoom;
      } else if (camera instanceof THREE.OrthographicCamera) {
        visibleHeight = (camera.top - camera.bottom) / camera.zoom;
      }
      const radius = visibleHeight * 7 / Math.max(1, viewportHeight);
      matrix.compose(position, rotation, scale.setScalar(radius));
      this.mesh.setMatrixAt(index, matrix);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
    this.mesh.computeBoundingSphere();
    this.mesh.updateMatrixWorld(true);
  }
  projectedAnchors(camera: THREE.Camera) {
    return this.anchors.map(anchor => {
      const point = anchor.position.clone().project(camera);
      return { id: anchor.id, label: anchor.label, ndc: point.toArray() };
    });
  }
  pick(x: number, y: number, camera: THREE.Camera): { id: string; label: string } | null {
    if (!this.mesh.visible) return null;
    this.raycaster.setFromCamera(new THREE.Vector2(x, y), camera);
    const hit = this.raycaster.intersectObject(this.mesh, false)[0];
    const anchor = hit?.instanceId === undefined ? null : this.anchors[hit.instanceId];
    return anchor ? { id: anchor.id, label: anchor.label } : null;
  }
  dispose() { this.mesh.removeFromParent(); this.mesh.geometry.dispose(); this.mesh.material.dispose(); }
}
