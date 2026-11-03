import * as THREE from "three";
import type { City, Signal, SignalGeometry } from "./types.ts";
interface Movement {
  signalId: string;
  index: number;
  position: THREE.Vector3;
  rotation: THREE.Quaternion;
  spread: THREE.Vector3;
  state: string | undefined;
}
/** Symbolic per-controlled-link arrows, placed from actual exported SUMO lane shapes. */
export class GeometryLayer {
  readonly group = new THREE.Group();
  private movements: Movement[] = [];
  private arrows: THREE.InstancedMesh | null = null;
  private backings: THREE.InstancedMesh | null = null;
  private disposables: Array<{ dispose: () => void }> = [];
  setGeometry(
    city: City | null,
    routeEdges: string[],
    signals: SignalGeometry[],
  ) {
    this.clear();
    if (city && routeEdges.length) {
      const edges = new Map(city.edges.map((e) => [e.id, e]));
      const points: number[] = [];
      // Route is canonical road-center reference, not a fabricated lane trajectory.
      for (const id of routeEdges) {
        const edge = edges.get(id);
        if (!edge) continue;
        for (let i = 1; i < edge.centerline.length; i++) {
          const a = edge.centerline[i - 1],
            b = edge.centerline[i];
          points.push(a[0], 0.8, -a[1], b[0], 0.8, -b[1]);
        }
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(points, 3),
      );
      const material = new THREE.LineBasicMaterial({
        color: 0x78d9cb,
        transparent: true,
        opacity: 0.8,
      });
      this.group.add(new THREE.LineSegments(geometry, material));
      this.disposables.push(geometry, material);
    }
    const arrow = new THREE.Shape();
    arrow.moveTo(0, -3.5);
    arrow.lineTo(1.5, -1);
    arrow.lineTo(0.65, -1);
    arrow.lineTo(0.65, 2.5);
    arrow.lineTo(-0.65, 2.5);
    arrow.lineTo(-0.65, -1);
    arrow.lineTo(-1.5, -1);
    arrow.closePath();
    const geometry = new THREE.ShapeGeometry(arrow);
    this.disposables.push(geometry);
    for (const signal of signals) {
      const lanes = new Map<string, typeof signal.links>();
      for (const link of signal.links) {
        const list = lanes.get(link.from_lane) ?? [];
        list.push(link);
        lanes.set(link.from_lane, list);
      }
      for (const links of lanes.values())
        for (let i = 0; i < links.length; i++) {
          const link = links[i],
            shape = link.incoming_shape;
          if (shape.length < 2) continue;
          const a = shape[shape.length - 2],
            b = shape[shape.length - 1],
            dx = b[0] - a[0],
            dy = b[1] - a[1],
            length = Math.hypot(dx, dy);
          if (!length) continue;
          const offset = (i - (links.length - 1) / 2) * 1.4;
          const x = b[0] - (dx / length) * 5 - (dy / length) * offset,
            y = b[1] - (dy / length) * 5 + (dx / length) * offset;
          const outgoing = link.outgoing_shape;
          const outA = outgoing[0],
            outB = outgoing[1];
          const rotation = new THREE.Quaternion().setFromEuler(
            new THREE.Euler(
              -Math.PI / 2,
              0,
              Math.atan2(outB[0] - outA[0], -(outB[1] - outA[1])),
            ),
          );
          this.movements.push({
            signalId: signal.id,
            index: link.index,
            position: new THREE.Vector3(x, 0.32, -y),
            rotation,
            spread: new THREE.Vector3(
              -(dy / length) * offset,
              0,
              -(dx / length) * offset,
            ),
            state: undefined,
          });
        }
    }
    if (this.movements.length) {
      const material = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        side: THREE.DoubleSide,
        depthTest: true,
        depthWrite: false,
        toneMapped: false,
      });
      const backing = new THREE.MeshBasicMaterial({
        color: 0x101c2b,
        side: THREE.DoubleSide,
        depthTest: true,
        depthWrite: false,
        toneMapped: false,
      });
      this.arrows = new THREE.InstancedMesh(
        geometry,
        material,
        this.movements.length,
      );
      this.backings = new THREE.InstancedMesh(
        geometry,
        backing,
        this.movements.length,
      );
      this.arrows.name = "Per-controlled-link signal arrows";
      this.backings.name = "Signal contrast outlines";
      this.arrows.renderOrder = 6;
      this.backings.renderOrder = 5;
      for (const mesh of [this.backings, this.arrows]) {
        mesh.count = 0;
        mesh.frustumCulled = false;
        mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        this.group.add(mesh);
        this.disposables.push(mesh);
      }
      this.disposables.push(material, backing);
    }
  }
  update(signals: Signal[]) {
    const states = new Map(signals.map((s) => [s.id, s.state]));
    for (const movement of this.movements)
      movement.state = states.get(movement.signalId)?.[movement.index];
  }
  /** Symbolic overlay size, not a road marking or a whole-junction phase. */
  updatePresentation(camera: THREE.Camera, viewportHeight: number) {
    if (!this.arrows || !this.backings) return;
    camera.updateMatrixWorld(true);
    const matrix = new THREE.Matrix4(),
      scale = new THREE.Vector3(),
      color = new THREE.Color();
    let index = 0;
    for (const movement of this.movements) {
      if (!movement.state) continue;
      const depth = -movement.position
        .clone()
        .applyMatrix4(camera.matrixWorldInverse).z;
      if (depth <= 0) continue;
      const height =
        camera instanceof THREE.PerspectiveCamera
          ? (2 * depth * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) /
            camera.zoom
          : camera instanceof THREE.OrthographicCamera
            ? (camera.top - camera.bottom) / camera.zoom
            : 1;
      // A movement glyph stays within its real approach. At city scale these
      // become small colored marks; they must never grow into roof-sized icons.
      let size = signalSymbolScale(height, viewportHeight);
      const aspect =
        camera instanceof THREE.PerspectiveCamera
          ? camera.aspect
          : camera instanceof THREE.OrthographicCamera
            ? (camera.right - camera.left) / (camera.top - camera.bottom)
            : 1;
      // Account for ground-plane foreshortening; a low orbit must not flatten
      // the movement symbol into an unreadable hairline.
      const projected = (axis: THREE.Vector3) => {
        axis.applyQuaternion(movement.rotation);
        const a = movement.position.clone().add(axis).project(camera);
        const b = movement.position.clone().sub(axis).project(camera);
        return Math.hypot(
          ((a.x - b.x) * viewportHeight * aspect) / 2,
          ((a.y - b.y) * viewportHeight) / 2,
        );
      };
      const pixels = Math.max(
        projected(new THREE.Vector3(0, 3, 0)),
        projected(new THREE.Vector3(1.5, 0, 0)),
      );
      if (Number.isFinite(pixels) && pixels > 0)
        size = THREE.MathUtils.clamp(8 / pixels, 0.25, 0.8);
      const position = movement.position;
      matrix.compose(position, movement.rotation, scale.set(size, size, size));
      this.arrows.setMatrixAt(index, matrix);
      color.set(signalColor(movement.state));
      this.arrows.setColorAt(index, color);
      matrix.compose(
        position,
        movement.rotation,
        scale.set(size * 1.16, size * 1.1, size),
      );
      this.backings.setMatrixAt(index, matrix);
      index++;
    }
    for (const mesh of [this.arrows, this.backings]) {
      mesh.count = index;
      mesh.instanceMatrix.needsUpdate = true;
    }
    if (this.arrows.instanceColor) this.arrows.instanceColor.needsUpdate = true;
  }
  /** Explicit QA only: read the actual displayed controlled-link color buffers. */
  inspectSignals(ids: ReadonlySet<string>, camera: THREE.Camera) {
    const result: Array<{ signalId: string; linkIndex: number; color: string }> = [];
    if (!this.arrows || !ids.size) return result;
    let index = 0;
    const color = new THREE.Color();
    for (const movement of this.movements) {
      if (!movement.state) continue;
      const depth = -movement.position.clone().applyMatrix4(camera.matrixWorldInverse).z;
      if (depth <= 0) continue;
      if (ids.has(movement.signalId) && index < this.arrows.count) {
        this.arrows.getColorAt(index, color);
        result.push({ signalId: movement.signalId, linkIndex: movement.index,
          color: `#${color.getHexString()}` });
      }
      index++;
    }
    return result;
  }
  private clear() {
    this.group.clear();
    this.movements = [];
    this.arrows = null;
    this.backings = null;
    for (const item of this.disposables) item.dispose();
    this.disposables = [];
  }
  dispose() {
    this.clear();
  }
}

/** Approximate 8 px longest axis, never larger than a 4.8 m movement glyph. */
export function signalSymbolScale(
  visibleHeight: number,
  viewportHeight: number,
): number {
  if (
    !Number.isFinite(visibleHeight) ||
    !Number.isFinite(viewportHeight) ||
    viewportHeight <= 0
  )
    return 1;
  return THREE.MathUtils.clamp(
    (visibleHeight * 8) / viewportHeight / 6,
    0.25,
    0.8,
  );
}
export function signalColor(state: string): string {
  return state === "G" || state === "g"
    ? "#78D9CB"
    : state === "y" || state === "Y"
      ? "#FFB85C"
      : state === "r" || state === "R"
        ? "#ED8B82"
        : "#B4C1CE";
}
