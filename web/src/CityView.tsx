import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MapControls } from "three/addons/controls/MapControls.js";
import type { City, Frame } from "./types.ts";
import { vehiclePose } from "./replay.ts";

interface Props {
  city: City | null;
  frame: Frame | null;
  ghostFrame: Frame | null;
  ghost: boolean;
  ghostOpacity: number;
  pickup: string;
  hospital: string;
  quality: "balanced" | "high";
  follow: boolean;
  reducedMotion: boolean;
  reset: number;
  world: string;
}
const base = import.meta.env.BASE_URL;
export function CityView(props: Props) {
  const host = useRef<HTMLDivElement>(null);
  const current = useRef(props);
  current.current = props;
  const [status, setStatus] = useState("Loading original city assets…");
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const container = host.current!;
    let disposed = false,
      dirty = true,
      modelsRevision = 0;
    let renderer: THREE.WebGLRenderer;
    setFailed(false);
    setStatus("Loading original city assets…");
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
    } catch {
      setFailed(true);
      setStatus(
        "3D rendering is unavailable. The original city preview and evidence remain available.",
      );
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.setClearColor(0x101c2b, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.35;
    renderer.domElement.setAttribute(
      "aria-label",
      "Interactive original AFTERLIGHT city. Drag to pan, scroll to zoom. Use the HTML controls to select a pickup and hospital.",
    );
    renderer.domElement.setAttribute("role", "img");
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-850, 850, 650, -650, 1, 5000);
    const overview = () => {
      camera.position.set(1050, 1250, 1100);
      camera.zoom = 1;
      camera.updateProjectionMatrix();
      controls.target.set(0, 0, 0);
      controls.update();
    };
    const controls = new MapControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.minZoom = 0.65;
    controls.maxZoom = 12;
    controls.maxPolarAngle = Math.PI * 0.44;
    controls.minPolarAngle = Math.PI * 0.12;
    overview();
    controls.addEventListener("change", () => {
      dirty = true;
    });
    scene.add(new THREE.HemisphereLight(0xc3daec, 0x4b5661, 2.1));
    const sun = new THREE.DirectionalLight(0xffe4c2, 3.2);
    sun.position.set(-450, 900, 200);
    scene.add(sun);
    const rim = new THREE.DirectionalLight(0x89bad5, 1.8);
    rim.position.set(500, 350, -550);
    scene.add(rim);
    const selected = new THREE.Group();
    scene.add(selected);
    const marker = (color: number) => {
      const g = new THREE.Group();
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(9, 12, 40),
        new THREE.MeshBasicMaterial({
          color,
          side: THREE.DoubleSide,
          depthTest: false,
        }),
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 1.5;
      ring.renderOrder = 4;
      g.add(ring);
      const pin = new THREE.Mesh(
        new THREE.CylinderGeometry(1.2, 1.2, 30, 8),
        new THREE.MeshBasicMaterial({ color }),
      );
      pin.position.y = 16;
      g.add(pin);
      return g;
    };
    const pickupMarker = marker(0xffb85c),
      hospitalMarker = marker(0x78d9cb);
    selected.add(pickupMarker, hospitalMarker);
    pickupMarker.visible = false;
    hospitalMarker.visible = false;
    const active = new THREE.Group(),
      ghosts = new THREE.Group(),
      signalGroup = new THREE.Group();
    scene.add(active, ghosts, signalGroup);
    const models = new Map<string, THREE.Group>();
    const pools = new Map<string, THREE.Group>();
    const ghostModels = new Map<string, THREE.Group>();
    const signals = new Map<string, THREE.Mesh>();
    const loader = new GLTFLoader();
    const ownedMaterials = new Set<THREE.Material>();
    const load = async () => {
      try {
        const gltf = await loader.loadAsync(
          `${base}assets/exports/city_static.glb`,
        );
        if (disposed) {
          disposeObject(gltf.scene);
          return;
        }
        // Preserve the authored root translation. Never center or replace glTF transforms.
        scene.add(gltf.scene);
        dirty = true;
        setStatus("");
        await Promise.all(
          ["ambulance", "car", "truck", "bike"].map(async (type) => {
            const glb = await loader.loadAsync(
              `${base}assets/exports/${type}.glb`,
            );
            if (disposed) {
              disposeObject(glb.scene);
              return;
            }
            models.set(type, glb.scene);
            modelsRevision++;
            dirty = true;
          }),
        );
      } catch (error) {
        if (!disposed) {
          setFailed(true);
          setStatus(
            `City assets could not load. ${error instanceof Error ? error.message : "Check the connection and retry."}`,
          );
        }
      }
    };
    void load();
    const resize = () => {
      dirty = true;
      const { width, height } = container.getBoundingClientRect();
      renderer.setSize(width, height, false);
      const aspect = width / Math.max(height, 1);
      camera.left = -670 * aspect;
      camera.right = 670 * aspect;
      camera.top = 670;
      camera.bottom = -670;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    const contextLost = (e: Event) => {
      e.preventDefault();
      setFailed(true);
      setStatus(
        "The 3D graphics context was interrupted. Retry to restore the city. Playback evidence remains available.",
      );
    };
    renderer.domElement.addEventListener("webglcontextlost", contextLost);
    let lastReset = current.current.reset,
      lastQuality = "",
      lastProps: Props | null = null,
      lastModelsRevision = -1;
    let raf = 0;
    const setVehicles = (
      frame: Frame | null,
      pool: Map<string, THREE.Group>,
      parent: THREE.Group,
      ghost: boolean,
    ) => {
      for (const o of pool.values()) o.visible = false;
      for (const v of frame?.vehicles ?? []) {
        if (ghost && v.type !== "ambulance" && v.id !== "ambulance") continue;
        let o = pool.get(v.id);
        const type =
          v.type === "ambulance" || v.id === "ambulance"
            ? "ambulance"
            : models.has(v.type)
              ? v.type
              : "car";
        if (!o) {
          const template = models.get(type);
          if (!template) continue;
          o = new THREE.Group();
          const model = template.clone(true);
          if (ghost)
            model.traverse((child) => {
              if (child instanceof THREE.Mesh) {
                const mats = (
                  Array.isArray(child.material)
                    ? child.material
                    : [child.material]
                ).map(() => {
                  const m = new THREE.MeshBasicMaterial({
                    color: 0x87d7ff,
                    transparent: true,
                    opacity: current.current.ghostOpacity,
                    depthWrite: false,
                  });
                  ownedMaterials.add(m);
                  return m;
                });
                child.material = Array.isArray(child.material) ? mats : mats[0];
                child.renderOrder = 3;
              }
            });
          o.add(model);
          pool.set(v.id, o);
          parent.add(o);
        }
        const [x, y, z, rotation] = vehiclePose(v);
        o.position.set(x, y + 0.12, z);
        o.rotation.y = rotation;
        o.visible = true;
        if (ghost)
          o.traverse((child) => {
            if (child instanceof THREE.Mesh)
              for (const m of Array.isArray(child.material)
                ? child.material
                : [child.material])
                m.opacity = current.current.ghostOpacity;
          });
      }
    };
    const loop = () => {
      if (disposed) return;
      const p = current.current;
      const changed = p !== lastProps || modelsRevision !== lastModelsRevision;
      if (changed) {
        dirty = true;
        if (lastReset !== p.reset) {
          overview();
          lastReset = p.reset;
        }
        if (lastQuality !== p.quality) {
          renderer.setPixelRatio(
            Math.min(devicePixelRatio, p.quality === "high" ? 2 : 1.25),
          );
          lastQuality = p.quality;
          resize();
        }
        if (
          p.frame !== lastProps?.frame ||
          modelsRevision !== lastModelsRevision
        )
          setVehicles(p.frame, pools, active, false);
        if (
          p.ghostFrame !== lastProps?.ghostFrame ||
          p.ghost !== lastProps?.ghost ||
          p.world !== lastProps?.world ||
          p.ghostOpacity !== lastProps?.ghostOpacity ||
          modelsRevision !== lastModelsRevision
        )
          setVehicles(
            p.ghost && p.world === "afterlight" ? p.ghostFrame : null,
            ghostModels,
            ghosts,
            true,
          );
        const point = p.city?.pickups.find((x) => x.id === p.pickup)?.position;
        pickupMarker.visible = Boolean(point);
        if (point)
          pickupMarker.position.set(point[0], point[2] ?? 0, -point[1]);
        const h = p.city?.hospitals.find((x) => x.id === p.hospital);
        const hp =
          h && p.city?.nodes.find((n) => n.id === h.destination_node)?.position;
        hospitalMarker.visible = Boolean(hp);
        if (hp) hospitalMarker.position.set(hp[0], hp[2] ?? 0, -hp[1]);
        for (const s of signals.values()) s.visible = false;
        for (const signal of p.frame?.signals ?? []) {
          const n = p.city?.nodes.find((n) => n.id === signal.id);
          if (!n) continue;
          let dot = signals.get(signal.id);
          if (!dot) {
            dot = new THREE.Mesh(
              new THREE.SphereGeometry(3.5, 8, 6),
              new THREE.MeshBasicMaterial(),
            );
            signals.set(signal.id, dot);
            signalGroup.add(dot);
          }
          dot.visible = true;
          dot.position.set(n.position[0], 5, -n.position[1]);
          (dot.material as THREE.MeshBasicMaterial).color.set(
            "#B4C1CE",
          ); /* Neutral marker: multi-link phase is not a universal green. */
        }
        if (p.follow && !p.reducedMotion) {
          if (!lastProps?.follow) {
            camera.zoom = 4;
            camera.updateProjectionMatrix();
          }
          const ambulance = p.frame?.vehicles.find(
            (v) => v.type === "ambulance" || v.id === "ambulance",
          );
          if (ambulance) {
            const [x, , z] = vehiclePose(ambulance);
            const delta = new THREE.Vector3(x, 0, z).sub(controls.target);
            camera.position.add(delta);
            controls.target.add(delta);
          }
        }
        lastProps = p;
        lastModelsRevision = modelsRevision;
      }
      controls.update();
      if (dirty) {
        renderer.render(scene, camera);
        dirty = false;
      }
      raf = requestAnimationFrame(loop);
    };
    loop();
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("webglcontextlost", contextLost);
      disposeObject(scene);
      for (const model of models.values()) disposeObject(model);
      for (const m of ownedMaterials) m.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [retry]);
  return (
    <div className="city-view">
      <div className="three-host" ref={host} />
      {failed && (
        <img
          className="city-fallback"
          src={`${base}assets/previews/city_overview.png`}
          alt="Blender authoring preview of the original 25-junction city; not a running simulation"
        />
      )}
      {status && (
        <div className="canvas-status" role="status">
          <p>{status}</p>
          {failed && (
            <button onClick={() => setRetry((x) => x + 1)}>
              Retry 3D city
            </button>
          )}
        </div>
      )}
      <div className="map-compass" aria-hidden="true">
        <svg viewBox="0 0 40 56">
          <path d="M20 10 29 36 20 30 11 36Z" fill="currentColor" />
          <text x="20" y="7" textAnchor="middle">
            N
          </text>
        </svg>
      </div>
    </div>
  );
}
function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.geometry.dispose();
      for (const m of Array.isArray(child.material)
        ? child.material
        : [child.material])
        m.dispose();
    }
  });
}
