import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
interface Building { bounds: THREE.Box3; faded: boolean }
/** Only authored building nodes enter these batches. Ground and shared-color trees never do. */
export class BuildingCutaway {
  private buildings: Building[] = [];
  private opacityTexture: THREE.DataTexture | null = null;
  private opacityBytes = new Uint8Array();
  readonly batches = new THREE.Group();
  private pendingGeometry = new Set<THREE.BufferGeometry>();
  get count() { return this.buildings.length; }
  install(root: THREE.Object3D) {
    try { this.installAsset(root); }
    catch (error) { this.dispose(); throw error; }
  }
  private installAsset(root: THREE.Object3D) {
    root.updateMatrixWorld(true);
    const nodes: THREE.Object3D[] = [];
    const ids = new Set<string>();
    root.traverse((node) => {
      if (node.userData.occluder !== true && !node.name.startsWith("AL_BUILDING_")) return;
      const id = node.userData.building_id ?? (node.name.startsWith("AL_BUILDING_") ? node.name.slice("AL_BUILDING_".length) : null);
      if (typeof id !== "string" || !id.trim()) throw new Error("Building asset is missing a stable building ID.");
      if (ids.has(id)) throw new Error(`Building asset repeats building ID ${id}.`);
      ids.add(id);
      for (let parent = node.parent; parent && parent !== root; parent = parent.parent)
        if (parent.userData.occluder === true || parent.name.startsWith("AL_BUILDING_")) return;
      nodes.push(node);
    });
    if (!nodes.length) throw new Error("Enhanced city asset has no addressable building geometry.");
    this.opacityBytes = new Uint8Array(nodes.length * 4).fill(255);
    this.opacityTexture = new THREE.DataTexture(this.opacityBytes, nodes.length, 1, THREE.RGBAFormat);
    this.opacityTexture.minFilter = THREE.NearestFilter;
    this.opacityTexture.magFilter = THREE.NearestFilter;
    this.opacityTexture.generateMipmaps = false;
    this.opacityTexture.needsUpdate = true;
    const groups = new Map<THREE.Material, THREE.BufferGeometry[]>();
    nodes.forEach((node, index) => {
      const bounds = new THREE.Box3().setFromObject(node);
      this.buildings.push({ bounds, faded: false });
      node.traverse((child) => {
        if (!(child instanceof THREE.Mesh)) return;
        // glTF material primitives load as single-material child meshes.
        if (Array.isArray(child.material)) throw new Error("Building asset must expose one material per primitive.");
        const geometry = child.geometry.index ? child.geometry.toNonIndexed() : child.geometry.clone();
        this.pendingGeometry.add(geometry);
        geometry.applyMatrix4(child.matrixWorld); // Preserve every authored parent/root transform exactly.
        if (!geometry.hasAttribute("normal")) geometry.computeVertexNormals();
        const count = geometry.getAttribute("position").count;
        if (!geometry.hasAttribute("uv")) geometry.setAttribute("uv", new THREE.Float32BufferAttribute(new Float32Array(count * 2), 2));
        // Static authored assets use position/normal/UV; vertex color remains supported.
        const usesColor = "vertexColors" in child.material && child.material.vertexColors;
        if (usesColor && !geometry.hasAttribute("color")) geometry.setAttribute("color", new THREE.Float32BufferAttribute(new Float32Array(count * 3).fill(1), 3));
        for (const name of Object.keys(geometry.attributes))
          if (!["position", "normal", "uv", ...(usesColor ? ["color"] : [])].includes(name)) geometry.deleteAttribute(name);
        geometry.setAttribute("afterlightBuildingU", new THREE.Float32BufferAttribute(new Float32Array(count).fill((index + 0.5) / nodes.length), 1));
        const parts = groups.get(child.material) ?? [];
        parts.push(geometry);
        groups.set(child.material, parts);
      });
    });
    for (const [source, parts] of groups) {
      const geometry = mergeGeometries(parts, false);
      for (const part of parts) { part.dispose(); this.pendingGeometry.delete(part); }
      if (!geometry) throw new Error("Building render batches have incompatible geometry.");
      const material = source.clone();
      material.onBeforeCompile = (shader) => {
        shader.uniforms.afterlightBuildingOpacity = { value: this.opacityTexture };
        shader.vertexShader = "attribute float afterlightBuildingU;\nvarying float afterlightU;\n" + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\nafterlightU = afterlightBuildingU;");
        shader.fragmentShader = "uniform sampler2D afterlightBuildingOpacity;\nvarying float afterlightU;\n" + shader.fragmentShader;
        shader.fragmentShader = shader.fragmentShader.replace("#include <clipping_planes_fragment>", `
          #include <clipping_planes_fragment>
          float buildingOpacity = texture2D(afterlightBuildingOpacity, vec2(afterlightU, 0.5)).r;
          float stipple = fract(dot(mod(floor(gl_FragCoord.xy), 4.0), vec2(0.25, 0.0625)));
          if (stipple >= buildingOpacity) discard;
        `);
      };
      material.customProgramCacheKey = () => "afterlight-whole-building-opacity-v1";
      const mesh = new THREE.Mesh(geometry, material);
      mesh.name = `AFTERLIGHT_BUILDING_BATCH_${source.name}`;
      this.batches.add(mesh);
    }
    // Hide only after every batch succeeds. Original asset nodes remain available for bounds/audit.
    for (const node of nodes) node.visible = false;
    root.parent?.add(this.batches); // Baked geometry is already in world space.
  }
  update(enabled: boolean, focus: THREE.Vector3, camera: THREE.Camera): number {
    const ray = new THREE.Ray();
    const hit = new THREE.Vector3();
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
    const targets = [focus, focus.clone().addScaledVector(right, 8), focus.clone().addScaledVector(right, -8),
      focus.clone().addScaledVector(up, 8), focus.clone().addScaledVector(up, -8)];
    let count = 0;
    for (let index = 0; index < this.buildings.length; index++) {
      const building = this.buildings[index];
      const faded = enabled && targets.some((target) => {
        const distance = camera.position.distanceTo(target);
        ray.set(camera.position, target.clone().sub(camera.position).normalize());
        return ray.intersectBox(building.bounds, hit) !== null && camera.position.distanceTo(hit) < distance - 2;
      });
      if (faded) count++;
      if (building.faded === faded) continue;
      building.faded = faded;
      this.opacityBytes[index * 4] = faded ? 36 : 255;
      if (this.opacityTexture) this.opacityTexture.needsUpdate = true;
    }
    return count;
  }
  dispose() {
    this.opacityTexture?.dispose();
    this.opacityTexture = null;
    for (const geometry of this.pendingGeometry) geometry.dispose();
    this.pendingGeometry.clear();
    this.batches.removeFromParent();
    this.batches.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      child.geometry.dispose();
      for (const material of Array.isArray(child.material) ? child.material : [child.material]) material.dispose();
    });
    this.batches.clear();
    this.buildings = [];
  }
}
