# Blender / MCP production pipeline

**Status:** design only. Blender MCP installation, connection and runtime capability are unverified. Do not claim an asset was generated through MCP until the actual tool session is verified.

## Role and trust boundary

Blender MCP is an authoring bridge, not a frontend framework or a requirement for public hosting. The current upstream project is `ahujasid/mcp-for-blender` (the older `blender-mcp` URL redirects). It is third-party software, not an official Blender Foundation service. Pin and review the exact revision before installation. Do not expose its command socket beyond loopback. Installation, credentials and security changes require the appropriate authorization; this documentation does not perform them.

Review telemetry behavior against the pinned release. Upstream describes opt-in content telemetry, default anonymous usage reporting and `DISABLE_TELEMETRY=true`; verify actual configuration rather than assuming defaults. No personal data, keys or private scenes belong in prompts or public artifacts.

## Asset plan

Author original procedural geometry: three-intersection road kit, lanes/stoplines, signals, restrained building silhouettes, civilian vehicle variants and one recognizable ambulance. Keep one metric scale. Organize collections by reusable object class; name origins and pivots predictably. Export camera-independent geometry, not a complete baked film masquerading as interaction.

GLB export uses applied transforms, sensible normals, simple PBR materials and small textures. Test one intersection and one vehicle in the web runtime before building the full city. Instances share geometry/materials. Bake complex procedural materials to supported textures when needed; do not expect Blender shader nodes or Cycles lighting to transfer directly to glTF.

## Sequence

1. Verify available Blender version and MCP connection without changing security settings.
2. Create a tiny metric-scale intersection and ambulance; save source `.blend` and generation script.
3. Export a GLB; inspect bounds, axes, normals, material appearance and file size in the intended viewer.
4. Establish reusable modular pieces; build only the three intersections needed by the experiment.
5. Map canonical simulator trajectories to assets; compare stopline and turning alignment.
6. Add restrained lighting, route illumination, camera and afterglow queue visualization.
7. Test lower-power rendering and reduced-motion/static fallbacks.
8. Produce optional hero frames only after interactive replay is stable.

## Production budgets (targets)

First useful scene before a detailed city. Initial total downloaded hero assets target under 10 MiB; each deployed file must remain below the host’s 25 MiB limit. Target smooth desktop playback with instanced traffic and modest geometry; measure actual frame time on available hardware before promising FPS. Prefer a coherent silhouette over expensive textures, volumetrics, reflections or full-scene motion blur.

## Licensing and reproducibility

Maintain an asset provenance table listing filename, author, source, license and modifications. Original procedural assets are preferred. Do not import unrelated car-film assets with unknown rights. Include generation scripts and source scene where feasible, but no caches, recordings or credentials by accident. Choose project/asset licenses deliberately before publication; third-party dependencies retain their own licenses.

## Cut list

Cut first: photoreal façades, weather, individual wheel animation, volumetric fog, custom skeletal characters, long Cycles renders. Preserve: readable traffic states, ambulance identity, paired timing, aftermath reveal and evidence controls.

## Pass 3 coordinate and playback contract

Derive a geometry manifest from the actual SUMO `.net.xml`: lane shapes/widths, junction polygons, controlled connections, stable IDs, origin and meters. Never draw roads independently and eyeball them into alignment. Preserve SUMO projection/location metadata; do not subtract `netOffset` twice.

For common origin `(ox,oy)`: SUMO `(x,y,z)` → Blender `(x−ox,y−oy,z)` → standard Y-up web `(x−ox,z,−(y−oy))`. Convert exactly once. SUMO vehicle position is front-bumper center, not mesh center. With heading `a` clockwise from north, forward is `(sin(a),0,−cos(a))`; center is mapped front minus forward × length/2. A local `−Z`-forward asset uses yaw `−a`. Test north/east/south/west and turns before city production.

Live and replay adapters share run ID, step, simulation time, ID, vehicle type/length/pose, signals, events and cumulative metrics. Interpolate position only for presentation and heading by shortest arc; do not use corner-cutting splines. Step-hold discrete signal states. Handle spawn/despawn/teleport/missing frames explicitly. Live disconnect pauses with a disconnected label; never substitute a replay silently.

## Export and browser gates

Use original neutral ambulance livery without assuming rights to protected emblems. Plain mesh modules plus runtime instancing are safer than experimental Geometry Nodes instance export. Blender procedural nodes, compositor and Cycles appearance do not transfer automatically. Use supported Principled/unlit materials, controlled texture color spaces and a real GLTFLoader test.

Initial targets: first scene transfer ≤5 MiB, essential 3D ≤10 MiB, each file <20 MiB safety margin, mostly 512–1024px textures (max 2048), overview ≤150k triangles, ≤100 single-view/180 paired draw calls. Target laptop p95 frame time ≤33ms, preferred ≤16.7ms, measured with declared device/resolution/worst demand; never promise universal 60 FPS. Cap device pixel ratio at 1.5, low mode 1. Use shared geometry/materials, explicit instance ID slots/bounds and one renderer with scissor views. Synchronised toggle is a fallback if paired rendering is too costly.

Run glTF validation and review warnings, then actual target-browser smoke tests; validator success alone does not guarantee appearance. Cold load, start/end seek, pause/resume, spawn/despawn, disconnection and asset-size checks are release gates.

The bridge defaults to an unauthenticated localhost socket (documented port 9876) and can execute arbitrary Python. Loopback and reviewed scripts matter; optional safe mode is not a sandbox. No installation or code-level security audit has been performed. Do not enable external asset-generation integrations merely to achieve visual polish.
