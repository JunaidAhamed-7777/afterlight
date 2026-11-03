import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MapControls } from "three/addons/controls/MapControls.js";
import type { City, Frame, SignalGeometry, World } from "./types.ts";
import { recordedSignalsAt } from "./signalTimeline.ts";
import { boundedBytes } from "./response.ts";
import { MapSelectionLayer, type MapPickMode } from "./MapSelectionLayer.ts";
import { GeometryLayer } from "./GeometryLayer.ts";
import { BuildingCutaway } from "./BuildingCutaway.ts";
import { CameraControls, type CameraAction } from "./CameraControls.tsx";
import {
  AmbulanceCameraTrack,
  cameraSeek,
  followBlend,
  MAX_CAMERA_ZOOM,
} from "./cameraFollow.ts";
import { fitOrthographic } from "./cameraFit.ts";
import { VehicleLayer } from "./VehicleLayer.ts";
import { interpolatedFrame } from "./replay.ts";

interface Props {
  city: City | null;
  frames: Frame[];
  baselineFrames: Frame[];
  followFrames: Frame[];
  onManualCamera: () => void;
  onMapReady: (ready: boolean) => void;
  onLoadState: (state: {
    completed: number;
    total: number;
    phase: string;
    error: boolean;
  }) => void;
  pickMode: MapPickMode;
  onMapPick: (mode: Exclude<MapPickMode, null>, id: string) => void;
  onCancelPick: () => void;
  clock: { current: number };
  routeEdges: string[];
  networkGeometry: SignalGeometry[];
  signalWorld: World | null;
  ghost: boolean;
  ghostOpacity: number;
  pickup: string;
  hospital: string;
  quality: "balanced" | "high";
  follow: boolean;
  playing: boolean;
  followTarget: "ambulance" | "ghost";
  canFollow: boolean;
  onFollow: (target: "ambulance" | "ghost") => void;
  reducedMotion: boolean;
  reset: number;
  locate: number;
  world: string;
}
const base = import.meta.env.BASE_URL;
export function CityView(props: Props) {
  const host = useRef<HTMLDivElement>(null);
  const compass = useRef<HTMLDivElement>(null);
  const current = useRef(props);
  current.current = props;
  const [status, setStatus] = useState("Loading original city assets…");
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [exploring, setExploring] = useState(true);
  const [pan, setPan] = useState(false);
  const [cutaway, setCutaway] = useState(false);
  const [occluderCount, setOccluderCount] = useState(0);
  const [hoverAnchor, setHoverAnchor] = useState("");
  const cameraAction = useRef<(action: CameraAction) => void>(() => {});
  const preferences = useRef({ pan, cutaway });
  preferences.current = { pan, cutaway };
  useEffect(() => {
    const container = host.current!;
    const assetRequests = new AbortController();
    let disposed = false,
      halted = false,
      raf = 0,
      dirty = true,
      modelsRevision = 0,
      assetsLoaded = false,
      mapReady = false;
    current.current.onMapReady(false);
    let completedAssets = 0;
    current.current.onLoadState({
      completed: 0,
      total: 5,
      phase: "Loading city geometry",
      error: false,
    });
    const haltRuntime = (message: string) => {
      if (disposed || halted) return;
      halted = true;
      mapReady = false;
      current.current.onMapReady(false);
      cancelAnimationFrame(raf);
      setFailed(true);
      setStatus(message);
      current.current.onLoadState({
        completed: completedAssets,
        total: 5,
        phase: message,
        error: true,
      });
    };
    let renderer: THREE.WebGLRenderer;
    setFailed(false);
    setStatus("Loading original city assets…");
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
        // Millimetre road layers must remain stable across a two-kilometre city
        // while retaining the close inspection near plane.
        logarithmicDepthBuffer: true,
      });
    } catch {
      setFailed(true);
      setStatus(
        "3D rendering is unavailable. The original city preview and evidence remain available.",
      );
      current.current.onLoadState({
        completed: 0,
        total: 5,
        phase: "3D rendering is unavailable",
        error: true,
      });
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.setClearColor(0x101c2b, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // The city casts static shadows once; vehicle playback never redraws this map.
    renderer.shadowMap.autoUpdate = false;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.domElement.setAttribute(
      "aria-label",
      "Interactive original AFTERLIGHT city. Drag to orbit; use arrow keys or Pan mode to pan. Scroll or plus and minus zoom. X, Y, Z turn the camera; Shift reverses. Zero restores Full city. Tab leaves the map.",
    );
    renderer.domElement.setAttribute("role", "img");
    renderer.domElement.tabIndex = 0;
    renderer.domElement.setAttribute(
      "aria-keyshortcuts",
      "ArrowUp ArrowDown ArrowLeft ArrowRight + - 0 X Y Z",
    );
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const selectionLayer = new MapSelectionLayer();
    scene.add(selectionLayer.mesh);
    let pickingCamera: THREE.Camera | null = null;
    let pickingMode: MapPickMode = null;
    let pickingCity: City | null = null;
    let pointerStart: {
      id: number;
      x: number;
      y: number;
      dragged: boolean;
    } | null = null;
    let hoverLabel = "";
    const showHover = (label: string) => {
      if (label === hoverLabel) return;
      hoverLabel = label;
      setHoverAnchor(label);
    };
    const pickAt = (event: PointerEvent) => {
      const p = current.current;
      if (
        !p.pickMode ||
        p.pickMode !== pickingMode ||
        p.city !== pickingCity ||
        !pickingCamera ||
        halted
      )
        return null;
      const rect = renderer.domElement.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return null;
      return selectionLayer.pick(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        1 - ((event.clientY - rect.top) / rect.height) * 2,
        pickingCamera,
      );
    };
    const pointerDown = (event: PointerEvent) => {
      pointerStart =
        event.button === 0 && event.isPrimary && current.current.pickMode
          ? {
              id: event.pointerId,
              x: event.clientX,
              y: event.clientY,
              dragged: false,
            }
          : null;
    };
    const pointerMove = (event: PointerEvent) => {
      if (
        pointerStart &&
        Math.hypot(
          event.clientX - pointerStart.x,
          event.clientY - pointerStart.y,
        ) > 5
      )
        pointerStart.dragged = true;
      showHover(pickAt(event)?.label ?? "");
    };
    const pointerUp = (event: PointerEvent) => {
      const start = pointerStart;
      pointerStart = null;
      if (
        !start ||
        start.id !== event.pointerId ||
        start.dragged ||
        Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5
      )
        return;
      const picked = pickAt(event);
      const mode = current.current.pickMode;
      if (picked && mode) {
        showHover("");
        current.current.onMapPick(mode, picked.id);
      }
    };
    const cancelPointer = () => {
      pointerStart = null;
      showHover("");
    };
    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointermove", pointerMove);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    renderer.domElement.addEventListener("pointercancel", cancelPointer);
    renderer.domElement.addEventListener("pointerleave", cancelPointer);
    renderer.domElement.addEventListener("wheel", cancelPointer, {
      passive: true,
    });
    const projectedOrigin = new THREE.Vector3(),
      projectedNorth = new THREE.Vector3(),
      northDirection = new THREE.Vector3(0, 0, -100);
    let viewportWidth = 1,
      viewportHeight = 1;
    const camera = new THREE.OrthographicCamera(-850, 850, 650, -650, 1, 5000);
    const perspectiveCamera = new THREE.PerspectiveCamera(42, 1, 0.1, 10000);
    let renderCamera: THREE.Camera = camera;
    let perspectiveMode = true;
    let roll = 0;
    let overviewMode = true;
    let navigationTouched = false;
    const buildingCutaway = new BuildingCutaway();
    let assetBounds: THREE.Box3 | null = null;
    const cityBounds = () => {
      if (assetBounds) return assetBounds;
      const bounds = current.current.city?.bounds;
      if (!bounds)
        return new THREE.Box3(
          new THREE.Vector3(-650, 0, -650),
          new THREE.Vector3(650, 100, 650),
        );
      return new THREE.Box3(
        new THREE.Vector3(bounds.min[0], bounds.min[2] ?? 0, -bounds.max[1]),
        new THREE.Vector3(bounds.max[0], bounds.max[2] ?? 100, -bounds.min[1]),
      );
    };
    const fitOverview = () => {
      camera.updateMatrixWorld(true);
      const bounds = cityBounds();
      const points: Array<[number, number]> = [];
      for (const x of [bounds.min.x, bounds.max.x])
        for (const y of [bounds.min.y, bounds.max.y])
          for (const z of [bounds.min.z, bounds.max.z]) {
            const point = new THREE.Vector3(x, y, z).applyMatrix4(
              camera.matrixWorldInverse,
            );
            points.push([point.x, point.y]);
          }
      const fit = fitOrthographic(points, viewportWidth, viewportHeight);
      camera.left = -fit.halfWidth;
      camera.right = fit.halfWidth;
      camera.top = fit.halfHeight;
      camera.bottom = -fit.halfHeight;
      camera.updateProjectionMatrix();
    };
    let programmaticNavigation = false;
    const updateNavigation = () => {
      programmaticNavigation = true;
      try {
        controls.update();
      } finally {
        programmaticNavigation = false;
      }
    };
    const overview = () => {
      perspectiveMode = false;
      roll = 0;
      setExploring(false);
      overviewMode = true;
      const center = cityBounds().getCenter(new THREE.Vector3());
      camera.position.copy(center).add(new THREE.Vector3(1050, 1250, 1100));
      camera.zoom = 1;
      controls.target.copy(center);
      updateNavigation();
      fitOverview();
      dirty = true;
    };
    const controls = new MapControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.screenSpacePanning = true;
    controls.minZoom = 0.65;
    controls.maxZoom = MAX_CAMERA_ZOOM;
    controls.maxPolarAngle = Math.PI * 0.44;
    controls.minPolarAngle = Math.PI * 0.12;
    const explore = () => {
      overview();
      perspectiveMode = true;
      overviewMode = false;
      setExploring(true);
      camera.zoom = 2.5;
      const center = controls.target.clone();
      camera.position.copy(center).add(new THREE.Vector3(1050, 750, 1100));
      camera.updateProjectionMatrix();
      updateNavigation();
      dirty = true;
    };
    explore();
    controls.mouseButtons.LEFT = preferences.current.pan
      ? THREE.MOUSE.PAN
      : THREE.MOUSE.ROTATE;
    controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
    controls.touches.ONE = preferences.current.pan
      ? THREE.TOUCH.PAN
      : THREE.TOUCH.ROTATE;
    controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
    controls.listenToKeyEvents(renderer.domElement);
    const manualCamera = (breakFollow = false) => {
      navigationTouched = true;
      overviewMode = false;
      if (breakFollow) current.current.onManualCamera();
    };
    const cameraGesture = (event: PointerEvent) => {
      // Orbit and zoom adjust the locked view; deliberate pan releases it.
      manualCamera(
        event.button === 2 ||
          (event.button === 0 &&
            (preferences.current.pan ||
              event.ctrlKey ||
              event.metaKey ||
              event.shiftKey)),
      );
    };
    const cameraGestureStart = () => manualCamera();
    renderer.domElement.addEventListener("pointerdown", cameraGesture, true);
    controls.addEventListener("start", cameraGestureStart);
    cameraAction.current = (action) => {
      manualCamera(action === "overview" || action === "explore");
      if (action === "overview") {
        overview();
        return;
      }
      if (action === "explore") {
        explore();
        return;
      }
      if (action === "zoom-in" || action === "zoom-out") {
        camera.zoom = THREE.MathUtils.clamp(
          camera.zoom * (action === "zoom-in" ? 1.35 : 1 / 1.35),
          controls.minZoom,
          controls.maxZoom,
        );
        camera.updateProjectionMatrix();
        updateNavigation();
        dirty = true;
        return;
      }
      const direction = action.endsWith("+") ? 1 : -1;
      if (action.startsWith("z")) roll += (direction * Math.PI) / 18;
      else {
        const offset = camera.position.clone().sub(controls.target);
        const spherical = new THREE.Spherical().setFromVector3(offset);
        if (action.startsWith("x"))
          spherical.phi = THREE.MathUtils.clamp(
            spherical.phi + (direction * Math.PI) / 18,
            controls.minPolarAngle,
            controls.maxPolarAngle,
          );
        else spherical.theta += (direction * Math.PI) / 18;
        camera.position
          .copy(controls.target)
          .add(offset.setFromSpherical(spherical));
        updateNavigation();
      }
      dirty = true;
    };
    const cameraKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape" && current.current.pickMode) {
        event.preventDefault();
        cancelPointer();
        current.current.onCancelPick();
        return;
      }
      if (["x", "y", "z"].includes(event.key.toLowerCase())) {
        event.preventDefault();
        cameraAction.current(
          `${event.key.toLowerCase()}${event.shiftKey ? "-" : "+"}` as CameraAction,
        );
        return;
      }
      if (
        ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)
      ) {
        manualCamera(true);
        return;
      }
      if (!["+", "=", "-", "0"].includes(event.key)) return;
      event.preventDefault();
      manualCamera(event.key === "0");
      if (event.key === "0") overview();
      else {
        camera.zoom = THREE.MathUtils.clamp(
          camera.zoom * (event.key === "-" ? 1 / 1.2 : 1.2),
          controls.minZoom,
          controls.maxZoom,
        );
        camera.updateProjectionMatrix();
        updateNavigation();
      }
      dirty = true;
    };
    renderer.domElement.addEventListener("keydown", cameraKeys);
    const lastNavigationTarget = controls.target.clone();
    controls.addEventListener("change", () => {
      if (!programmaticNavigation && roll !== 0) {
        const delta = controls.target.clone().sub(lastNavigationTarget);
        if (delta.lengthSq() > 0) {
          const direction = camera.getWorldDirection(new THREE.Vector3());
          const correction = delta
            .clone()
            .applyAxisAngle(direction, -roll)
            .sub(delta);
          controls.target.add(correction);
          camera.position.add(correction);
          camera.updateMatrixWorld(true);
        }
      }
      lastNavigationTarget.copy(controls.target);
      dirty = true;
    });
    scene.add(new THREE.HemisphereLight(0xe4f4ff, 0x77956a, 1.4));
    const sun = new THREE.DirectionalLight(0xfff0cf, 2.2);
    sun.position.set(-450, 900, 200);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0003;
    sun.shadow.normalBias = 0.6;
    sun.shadow.camera.near = 2000;
    sun.shadow.camera.far = 6000;
    scene.add(sun);
    scene.add(sun.target);
    const rim = new THREE.DirectionalLight(0xadd8ff, 0.65);
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
    const inspectVehicles =
      new URLSearchParams(window.location.search).get("inspect") === "1";
    const inspectionIds = inspectVehicles
      ? (new URLSearchParams(window.location.search).get("inspect_ids") ?? "")
          .split(",")
          .filter((id) => /^[A-Za-z0-9_-]{1,80}$/.test(id))
          .slice(0, 16)
      : [];
    const inspectionSignals = inspectVehicles
      ? new Set(
          (
            new URLSearchParams(window.location.search).get(
              "inspect_signals",
            ) ?? ""
          )
            .split(",")
            .filter((id) => /^[A-Za-z0-9_-]{1,80}$/.test(id))
            .slice(0, 16),
        )
      : null;
    const active = new VehicleLayer(false, inspectVehicles, inspectionIds),
      ghosts = new VehicleLayer(true, inspectVehicles),
      signalGroup = new THREE.Group();
    scene.add(active.group, ghosts.group, signalGroup);
    const models = new Map<string, THREE.Group>();
    const geometryLayer = new GeometryLayer();
    scene.add(geometryLayer.group);
    const signals = new Map<string, THREE.Mesh>();
    const loader = new GLTFLoader();
    const loadAsset = async (name: string) => {
      const url = `${base}assets/exports/${name}.glb`;
      const response = await fetch(url, {
        signal: AbortSignal.any([
          assetRequests.signal,
          AbortSignal.timeout(60000),
        ]),
      });
      if (!response.ok)
        throw new Error(`${name} model request failed (${response.status}).`);
      const bytes = await boundedBytes(response, 50 * 1024 * 1024);
      if (disposed)
        throw new DOMException("City loading was canceled.", "AbortError");
      return loader.parseAsync(
        bytes.buffer,
        new URL(`${base}assets/exports/`, location.href).href,
      );
    };
    const load = async () => {
      try {
        const gltf = await loadAsset("city_enhanced");
        completedAssets++;
        current.current.onLoadState({
          completed: completedAssets,
          total: 5,
          phase: "Preparing city and vehicles",
          error: false,
        });
        if (disposed || halted) {
          disposeObject(gltf.scene);
          return;
        }
        // Preserve the authored root translation. Never center or replace glTF transforms.
        scene.add(gltf.scene);
        gltf.scene.updateMatrixWorld(true);
        const loadedBounds = new THREE.Box3().setFromObject(gltf.scene);
        if (!loadedBounds.isEmpty()) assetBounds = loadedBounds;
        buildingCutaway.install(gltf.scene);
        // Coplanar road/marking/park layers receive shadows but never cast them.
        // Building batches cast onto the city; excluding their own receivers
        // avoids shadow-map self-acne on miniature facade details.
        gltf.scene.traverse((node) => {
          if (node instanceof THREE.Mesh) {
            node.castShadow = false;
            node.receiveShadow = true;
          }
        });
        buildingCutaway.batches.traverse((node) => {
          if (node instanceof THREE.Mesh) {
            node.castShadow = true;
            node.receiveShadow = false;
          }
        });
        if (assetBounds) {
          const center = assetBounds.getCenter(new THREE.Vector3());
          const radius =
            Math.max(
              assetBounds.max.x - assetBounds.min.x,
              assetBounds.max.z - assetBounds.min.z,
            ) * 0.85;
          sun.position.copy(center).add(new THREE.Vector3(-1800, 3600, 800));
          sun.target.position.copy(center);
          Object.assign(sun.shadow.camera, {
            left: -radius,
            right: radius,
            top: radius,
            bottom: -radius,
          });
          sun.shadow.camera.updateProjectionMatrix();
        }
        renderer.shadowMap.needsUpdate = true;
        setOccluderCount(buildingCutaway.count);
        if (!current.current.follow && !navigationTouched && perspectiveMode)
          explore();
        else if (overviewMode && !current.current.follow) overview();
        dirty = true;
        setStatus("Loading original vehicle assets…");
        await Promise.all(
          ["ambulance", "car", "truck", "bike"].map(async (type) => {
            const glb = await loadAsset(type);
            if (disposed || halted) {
              disposeObject(glb.scene);
              return;
            }
            models.set(type, glb.scene);
            completedAssets++;
            current.current.onLoadState({
              completed: completedAssets,
              total: 5,
              phase: "Preparing vehicle models",
              error: false,
            });
            modelsRevision++;
            dirty = true;
          }),
        );
        if (!disposed && !halted) {
          assetsLoaded = true;
          current.current.onLoadState({
            completed: 5,
            total: 5,
            phase: "City ready",
            error: false,
          });
          setStatus("");
          dirty = true;
        }
      } catch (error) {
        haltRuntime(
          `City assets could not load. ${error instanceof Error ? error.message : "Check the connection and retry."}`,
        );
      }
    };
    void load();
    const resize = () => {
      if (disposed || halted) return;
      try {
        dirty = true;
        const { width, height } = container.getBoundingClientRect();
        if (width <= 0 || height <= 0) return;
        renderer.setSize(width, height, false);
        viewportWidth = width;
        viewportHeight = height;
        if (overviewMode && !current.current.follow) fitOverview();
        else {
          // Preserve the user's target, zoom and vertical scale during resizing.
          const halfHeight = (camera.top - camera.bottom) / 2;
          camera.left = (-halfHeight * width) / height;
          camera.right = (halfHeight * width) / height;
          camera.updateProjectionMatrix();
        }
      } catch (error) {
        haltRuntime(
          `The 3D view could not resize. ${error instanceof Error ? error.message : "Retry the city."}`,
        );
      }
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    const contextLost = (e: Event) => {
      e.preventDefault();
      haltRuntime(
        "The 3D graphics context was interrupted. Retry to restore the city. Playback evidence remains available.",
      );
    };
    renderer.domElement.addEventListener("webglcontextlost", contextLost);
    let lastReset = current.current.reset,
      lastLocate = current.current.locate,
      lastQuality = "",
      lastProps: Props | null = null,
      lastModelsRevision = -1,
      lastTime = -1,
      lastPan = pan,
      lastCutaway = cutaway;
    let followTrack = new AmbulanceCameraTrack(current.current.followFrames);
    let previousFollowTime: number | null = null;
    let previousTick = performance.now();
    let wasFollowing = false;
    const loop = () => {
      if (disposed || halted) return;
      const tick = performance.now();
      const elapsed = Math.max(0, (tick - previousTick) / 1000);
      previousTick = tick;
      try {
        const p = current.current;
        if (
          lastPan !== preferences.current.pan ||
          lastCutaway !== preferences.current.cutaway
        ) {
          lastPan = preferences.current.pan;
          lastCutaway = preferences.current.cutaway;
          controls.mouseButtons.LEFT = lastPan
            ? THREE.MOUSE.PAN
            : THREE.MOUSE.ROTATE;
          controls.touches.ONE = lastPan ? THREE.TOUCH.PAN : THREE.TOUCH.ROTATE;
          dirty = true;
        }
        const changed =
          p !== lastProps ||
          modelsRevision !== lastModelsRevision ||
          p.clock.current !== lastTime;
        const frame = changed
          ? interpolatedFrame(p.frames, p.clock.current)
          : null;
        const ghostFrame =
          changed && p.ghost && p.world === "afterlight"
            ? interpolatedFrame(p.baselineFrames, p.clock.current)
            : null;
        if (changed) {
          dirty = true;
          if (lastReset !== p.reset) {
            overview();
            lastReset = p.reset;
          }
          if (lastLocate !== p.locate) {
            const target = new AmbulanceCameraTrack(p.followFrames).target(
              p.clock.current,
            );
            if (target) {
              const point = new THREE.Vector3(...target);
              camera.position.add(point.clone().sub(controls.target));
              controls.target.copy(point);
              camera.zoom = Math.max(camera.zoom, 12);
              perspectiveMode = true;
              overviewMode = false;
              setExploring(true);
              camera.updateProjectionMatrix();
              updateNavigation();
            }
            lastLocate = p.locate;
          }
          if (lastQuality !== p.quality) {
            renderer.setPixelRatio(
              Math.min(devicePixelRatio, p.quality === "high" ? 1.5 : 1.25),
            );
            const shadowSize = p.quality === "high" ? 4096 : 2048;
            if (sun.shadow.mapSize.x !== shadowSize) {
              sun.shadow.map?.dispose();
              sun.shadow.map = null;
              sun.shadow.mapSize.set(shadowSize, shadowSize);
              renderer.shadowMap.needsUpdate = true;
            }
            lastQuality = p.quality;
            resize();
          }
          if (
            p.city !== lastProps?.city ||
            p.routeEdges !== lastProps?.routeEdges ||
            p.networkGeometry !== lastProps?.networkGeometry
          )
            geometryLayer.setGeometry(p.city, p.routeEdges, p.networkGeometry);
          const exactSignals = p.signalWorld
            ? recordedSignalsAt(
                p.signalWorld,
                p.clock.current,
                frame?.signals ?? [],
              )
            : (frame?.signals ?? []);
          geometryLayer.update(exactSignals);
          active.update(frame?.vehicles ?? [], models);
          ghosts.update(ghostFrame?.vehicles ?? [], models, p.ghostOpacity);
          const point = p.city?.pickups.find(
            (x) => x.id === p.pickup,
          )?.position;
          pickupMarker.visible = Boolean(point);
          if (point)
            pickupMarker.position.set(point[0], point[2] ?? 0, -point[1]);
          const h = p.city?.hospitals.find((x) => x.id === p.hospital);
          const hp =
            h &&
            p.city?.nodes.find((n) => n.id === h.destination_node)?.position;
          hospitalMarker.visible = Boolean(hp);
          if (hp) hospitalMarker.position.set(hp[0], hp[2] ?? 0, -hp[1]);
          for (const s of signals.values()) s.visible = false;
          for (const signal of p.networkGeometry.length ? [] : exactSignals) {
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
          lastProps = p;
          lastModelsRevision = modelsRevision;
          lastTime = p.clock.current;
        }
        if (active.updateBeacons(tick / 1000, p.playing && !p.reducedMotion))
          dirty = true;
        const replacedTrack = followTrack.frames !== p.followFrames;
        if (replacedTrack)
          followTrack = new AmbulanceCameraTrack(p.followFrames);
        const following = p.follow && !p.reducedMotion;
        if (following) {
          overviewMode = false;
          const point = followTrack.target(p.clock.current);
          if (point) {
            const destination = new THREE.Vector3(...point);
            const delta = destination.sub(controls.target);
            const discontinuity =
              replacedTrack ||
              cameraSeek(previousFollowTime, p.clock.current, elapsed);
            if (!discontinuity) delta.multiplyScalar(followBlend(elapsed, p.playing));
            if (delta.lengthSq() > 1e-8) {
              camera.position.add(delta);
              controls.target.add(delta);
              dirty = true;
            }
          }
        }
        previousFollowTime = following ? p.clock.current : null;
        if (wasFollowing !== following) dirty = true;
        wasFollowing = following;
        updateNavigation();
        if (dirty) {
          // Navigation stays unrolled; the presentation camera adds perspective and roll.
          // Neither camera changes canonical geometry or the shared simulation clock.
          if (perspectiveMode) {
            const targetHalfHeight =
              (camera.top - camera.bottom) / (2 * camera.zoom);
            const distance =
              targetHalfHeight /
              Math.tan(THREE.MathUtils.degToRad(perspectiveCamera.fov / 2));
            perspectiveCamera.position
              .copy(camera.position)
              .sub(controls.target)
              .normalize()
              .multiplyScalar(distance)
              .add(controls.target);
            perspectiveCamera.quaternion.copy(camera.quaternion);
            perspectiveCamera.aspect = viewportWidth / viewportHeight;
            perspectiveCamera.updateProjectionMatrix();
            renderCamera = perspectiveCamera;
          } else {
            renderCamera = camera;
          }
          const unrolled = renderCamera.quaternion.clone();
          renderCamera.rotateZ(roll);
          renderCamera.updateMatrixWorld(true);
          const focus = controls.target.clone();
          const forward = renderCamera.getWorldDirection(new THREE.Vector3());
          const groundDistance =
            Math.abs(forward.y) > 1e-6
              ? (2 - renderCamera.position.y) / forward.y
              : -1;
          const hasGroundFocus =
            Number.isFinite(groundDistance) && groundDistance > 0;
          if (p.follow && !p.reducedMotion) focus.y = 2;
          else if (hasGroundFocus)
            focus
              .copy(renderCamera.position)
              .addScaledVector(forward, groundDistance);
          const fadedBuildings = buildingCutaway.update(
            preferences.current.cutaway &&
              perspectiveMode &&
              camera.zoom > 1.3 &&
              hasGroundFocus,
            focus,
            renderCamera,
          );
          renderer.domElement.dataset.fadedBuildings = String(fadedBuildings);
          renderer.domElement.dataset.occluderBuildings = String(
            buildingCutaway.count,
          );
          selectionLayer.setAnchors(p.city, p.pickMode);
          selectionLayer.update(renderCamera, viewportHeight);
          pickingCamera = p.pickMode ? renderCamera.clone() : null;
          pickingMode = p.pickMode;
          pickingCity = p.city;
          if (!p.pickMode) showHover("");
          renderer.domElement.dataset.mapPickMode = p.pickMode ?? "none";
          renderer.domElement.dataset.mapAnchors = JSON.stringify(
            p.pickMode ? selectionLayer.projectedAnchors(renderCamera) : [],
          );
          geometryLayer.updatePresentation(renderCamera, viewportHeight);
          renderer.render(scene, renderCamera);
          if (inspectVehicles) {
            renderer.domElement.dataset.vehicleInspection = JSON.stringify({
              absoluteTime: p.clock.current,
              world: p.world,
              ghostRequested: p.ghost,
              active: active.inspect(),
              ghost: ghosts.inspect(),
              signalLinks: inspectionSignals
                ? geometryLayer.inspectSignals(inspectionSignals, renderCamera)
                : [],
            });
          }
          if (assetsLoaded && !mapReady) {
            mapReady = true;
            current.current.onMapReady(true);
          }
          renderer.domElement.dataset.cameraZoom = String(camera.zoom);
          // Inspectable actual asset bounds, for viewport-fit QA, never simulated evidence.
          if (assetBounds) {
            let maxX = 0,
              maxY = 0;
            for (const x of [assetBounds.min.x, assetBounds.max.x])
              for (const y of [assetBounds.min.y, assetBounds.max.y])
                for (const z of [assetBounds.min.z, assetBounds.max.z]) {
                  const corner = new THREE.Vector3(x, y, z).project(
                    renderCamera,
                  );
                  maxX = Math.max(maxX, Math.abs(corner.x));
                  maxY = Math.max(maxY, Math.abs(corner.y));
                }
            renderer.domElement.dataset.cityFit = JSON.stringify({
              source: "world-transformed original glTF bounds",
              overview: overviewMode,
              maxX,
              maxY,
              viewportWidth,
              viewportHeight,
            });
          }
          renderer.domElement.dataset.cameraTarget = controls.target
            .toArray()
            .join(",");
          projectedOrigin.copy(controls.target).project(renderCamera);
          projectedNorth
            .copy(controls.target)
            .add(northDirection)
            .project(renderCamera);
          const dx = (projectedNorth.x - projectedOrigin.x) * viewportWidth;
          const dy = -(projectedNorth.y - projectedOrigin.y) * viewportHeight;
          if (compass.current)
            compass.current.style.transform = `rotate(${(Math.atan2(dx, -dy) * 180) / Math.PI}deg)`;
          renderer.domElement.dataset.renderInfo = JSON.stringify({
            calls: renderer.info.render.calls,
            triangles: renderer.info.render.triangles,
            geometries: renderer.info.memory.geometries,
            textures: renderer.info.memory.textures,
            fadedBuildings,
            occluderBuildings: buildingCutaway.count,
            logarithmicDepth: renderer.capabilities.logarithmicDepthBuffer,
          });
          renderer.domElement.dataset.cameraPresentation = perspectiveMode
            ? "perspective"
            : "orthographic";
          renderer.domElement.dataset.cameraRoll = String(roll);
          const orbit = new THREE.Spherical().setFromVector3(
            camera.position.clone().sub(controls.target),
          );
          renderer.domElement.dataset.cameraAzimuth = String(orbit.theta);
          renderer.domElement.dataset.cameraElevation = String(
            Math.PI / 2 - orbit.phi,
          );
          renderer.domElement.dataset.cameraState = JSON.stringify({
            mode: perspectiveMode ? "perspective" : "orthographic",
            position: renderCamera.position.toArray(),
            quaternion: renderCamera.quaternion.toArray(),
            target: controls.target.toArray(),
            zoom: camera.zoom,
            roll,
            azimuth: orbit.theta,
            elevation: Math.PI / 2 - orbit.phi,
            viewport: [viewportWidth, viewportHeight],
          });
          renderCamera.quaternion.copy(unrolled);
          renderCamera.updateMatrixWorld(true);
          dirty = false;
        }
        raf = requestAnimationFrame(loop);
      } catch (error) {
        haltRuntime(
          `The 3D view stopped after a rendering error. ${error instanceof Error ? error.message : "Retry the city."} Recorded evidence remains available.`,
        );
      }
    };
    loop();
    return () => {
      disposed = true;
      assetRequests.abort();
      current.current.onMapReady(false);
      cancelAnimationFrame(raf);
      observer.disconnect();
      cameraAction.current = () => {};
      renderer.domElement.removeEventListener(
        "pointerdown",
        cameraGesture,
        true,
      );
      controls.removeEventListener("start", cameraGestureStart);
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", pointerDown);
      renderer.domElement.removeEventListener("pointermove", pointerMove);
      renderer.domElement.removeEventListener("pointerup", pointerUp);
      renderer.domElement.removeEventListener("pointercancel", cancelPointer);
      renderer.domElement.removeEventListener("pointerleave", cancelPointer);
      renderer.domElement.removeEventListener("wheel", cancelPointer);
      selectionLayer.dispose();
      renderer.domElement.removeEventListener("keydown", cameraKeys);
      renderer.domElement.removeEventListener("webglcontextlost", contextLost);
      geometryLayer.dispose();
      active.dispose();
      ghosts.dispose();
      buildingCutaway.dispose();
      disposeObject(scene);
      for (const model of models.values()) disposeObject(model);
      sun.shadow.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [retry]);
  return (
    <div className="city-view">
      <div className="three-host" ref={host} />
      {!status && !failed && (
        <CameraControls
          exploring={exploring}
          pan={pan}
          cutaway={cutaway}
          occluderCount={occluderCount}
          disabled={failed || Boolean(status)}
          canFollow={props.canFollow && !failed && !status}
          following={props.follow ? props.followTarget : null}
          onFollow={props.onFollow}
          onAction={(action) => cameraAction.current(action)}
          onPan={setPan}
          onCutaway={setCutaway}
        />
      )}
      {props.pickMode && !status && !failed && (
        <div className="map-pick-instructions">
          <strong>
            Choose a{" "}
            {props.pickMode === "pickup" ? "pickup marker" : "hospital marker"}
          </strong>
          <p>
            Click a highlighted marker. Dragging still moves the camera. Your
            route changes only after a click.
          </p>
          <span className="map-pick-hover" aria-hidden="true">
            {hoverAnchor || "Hover a marker to see its name"}
          </span>
          <button onClick={props.onCancelPick}>Cancel map selection</button>
          <small>Escape cancels. You can also use the journey dropdowns.</small>
        </div>
      )}
      {failed && (
        <img
          className="city-fallback"
          src={`${base}assets/previews/city_expanded.png`}
          alt="Blender authoring preview of the expanded city; not a running simulation"
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
      {!status && !failed && (
        <div
          className="map-compass"
          ref={compass}
          aria-hidden="true"
          title="Canonical north (+Y)"
        >
          <svg viewBox="0 0 40 56">
            <path d="M20 10 29 36 20 30 11 36Z" fill="currentColor" />
            <text x="20" y="7" textAnchor="middle">
              N
            </text>
          </svg>
        </div>
      )}
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
