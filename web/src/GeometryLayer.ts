import * as THREE from "three";
import type { City, Signal, SignalGeometry } from "./types.ts";
interface Movement {
  signalId: string;
  index: number;
  mesh: THREE.Mesh;
}
/** Symbolic per-controlled-link arrows, placed from actual exported SUMO lane shapes. */
export class GeometryLayer {
  readonly group = new THREE.Group();
  private movements: Movement[] = [];
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
          const offset = (i - (links.length - 1) / 2) * 2.3;
          const x = b[0] - (dx / length) * 5 - (dy / length) * offset,
            y = b[1] - (dy / length) * 5 + (dx / length) * offset;
          const material = new THREE.MeshBasicMaterial({
            color: 0xb4c1ce,
            side: THREE.DoubleSide,
            depthTest: false,
          });
          const mesh = new THREE.Mesh(geometry, material);
          mesh.position.set(x, 1.1, -y);
          mesh.rotation.x = -Math.PI / 2;
          // Shape points -Y before ground rotation; align its tip with the actual outgoing lane.
          const outgoing = link.outgoing_shape;
          const outA = outgoing[0],
            outB = outgoing[1];
          mesh.rotation.z = Math.atan2(outB[0] - outA[0], -(outB[1] - outA[1]));
          mesh.renderOrder = 5;
          this.group.add(mesh);
          this.disposables.push(material);
          this.movements.push({ signalId: signal.id, index: link.index, mesh });
        }
    }
  }
  update(signals: Signal[]) {
    const states = new Map(signals.map((s) => [s.id, s.state]));
    for (const movement of this.movements) {
      const state = states.get(movement.signalId)?.[movement.index];
      movement.mesh.visible = Boolean(state);
      (movement.mesh.material as THREE.MeshBasicMaterial).color.set(
        state === "G" || state === "g"
          ? "#78D9CB"
          : state === "y" || state === "Y"
            ? "#FFB85C"
            : state === "r" || state === "R"
              ? "#ED8B82"
              : "#B4C1CE",
      );
    }
  }
  private clear() {
    this.group.clear();
    this.movements = [];
    for (const item of this.disposables) item.dispose();
    this.disposables = [];
  }
  dispose() {
    this.clear();
  }
}
