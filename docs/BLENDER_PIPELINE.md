# Blender / MCP production pipeline

**Current asset status, November 3, 2026:** the expanded city was authored and
exported locally in Blender 5.2.2 LTS using the existing pinned MCP for Blender
1.8 addon and an actual `execute_code` roundtrip over `127.0.0.1:9876`.
`assets/src/bootstrap_mcp.py` verifies addon SHA-256
`8e193a249e2ed1262f3e794ee2254efd8e3d1f0224385245f2b989154c837083`
(upstream `febcd90ece59c3416d7c55fd3723cea46bcaa59d`) and disables external
asset services. The new generator is `assets/src/generate_city_v4.py`; editable
source is `assets/afterlight_city_expanded.blend`. The original Blender 4.3.2
prototype and V3 enhancement source are retained as historical source scenes.

The V4 export has 826 addressable buildings and 235,604 triangles, with original
colorful facades, mixed roofs, 411 trees, 288 streetlights, eight fountain parks,
32 benches and two distinct diagonal hospital landmarks. Its roads derive from
the canonical map, including the actual fourfold area expansion and 81 primary
junctions. Road surface remains exactly 0.18 m. No signal color or moving traffic
is baked into the geometry. Nine binary structural checks passed locally;
the current Khronos validator report is retained in
`assets/qa/city_expanded_gltf_audit.json`. Rendering/performance acceptance belongs
to the actual browser cohort and is not implied by these export checks.

## Role and trust boundary

Blender MCP is an authoring bridge, not a frontend framework or a requirement for public hosting. The current upstream project is `ahujasid/mcp-for-blender` (the older `blender-mcp` URL redirects). It is third-party software, not an official Blender Foundation service. Pin and review the exact revision before installation. Do not expose its command socket beyond loopback. Installation, credentials and security changes require the appropriate authorization; this documentation does not perform them.

Review telemetry behavior against the pinned release. Upstream describes opt-in content telemetry, default anonymous usage reporting and `DISABLE_TELEMETRY=true`; verify actual configuration rather than assuming defaults. No personal data, keys or private scenes belong in prompts or public artifacts.

## Historical prototype production notes

The remaining sections preserve the original smaller-city plan and review
checkpoints. Their 25-junction, file-size, hosting and not-yet-created wording is
historical. Current geometry is described above and in [assets/README.md](../assets/README.md);
the current 50 MB static product budget and Vercel delivery contract are in
[DEPLOYMENT.md](DEPLOYMENT.md).

## Original asset plan

Author original procedural geometry: 20–25-intersection modular road kit with a three-junction test fixture, lanes/stoplines, signals, restrained building silhouettes, civilian vehicle variants and one recognizable ambulance. Keep one metric scale. Organize collections by reusable object class; name origins and pivots predictably. Export camera-independent geometry, not a complete baked film masquerading as interaction.

GLB export uses applied transforms, sensible normals, simple PBR materials and small textures. Test one intersection and one vehicle in the web runtime before building the full city. Instances share geometry/materials. Bake complex procedural materials to supported textures when needed; do not expect Blender shader nodes or Cycles lighting to transfer directly to glTF.

## Sequence

1. Verify available Blender version and MCP connection without changing security settings.
2. Create a tiny metric-scale intersection and ambulance; save source `.blend` and generation script.
3. Export a GLB; inspect bounds, axes, normals, material appearance and file size in the intended viewer.
4. Establish reusable modular pieces; assemble the authoritative city graph only after the three-junction fixture aligns.
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

## Expanded low-poly asset requirements and sequencing

This final documentation revision precedes further Blender creation. Planned asset work resumes only after the revised contracts are accepted/published. Do not treat parallel planning as permission to race ahead with a different map.

Create reusable cuboid building archetypes with vertex/instance color variation, simple car/truck/bike archetypes, two hospital landmarks and one more detailed stylized ambulance. The baseline ghost reuses the ambulance mesh with a dedicated cheap cyan translucent material; it is not a second separately authored high-cost model. Keep wheels and tiny fittings static unless they materially improve close-up readability. Never use protected emergency emblems by assumption.

Proposed geometry budgets: building archetype 12–300 triangles; civilian car/truck/bike 100–600 each; ambulance 2,000–5,000; hospital landmark 500–2,000. These are asset targets to validate in export, not achieved counts. Share material palettes and mesh instances; avoid one unique texture/material per building. Use simple LOD meshes or hide small props at overview scale; retain signal/route meaning in every LOD. Static repeated scenery is batched by spatial zone, moving vehicles instanced with correct ID slots/bounds.

Keep prior whole-scene ≤150k visible triangles, ≤100 draw calls for primary overlay and ≤180 optional paired-view targets. The full map may exceed them without LOD, so validate worst camera/demand rather than summing only archetype geometry. Prefer ghost overlay over duplicate whole-city rendering. Initial target GPU-resident geometry/textures ≤128 MiB on the test configuration, with estimated allocation documented and no leak across repeated scenario changes; available browser GPU memory is not universally observable. Record renderer counters plus process/device evidence, not an invented exact VRAM reading.

Maintain initial scene ≤5 MiB transfer, essential 3D ≤10 MiB, individual file <20 MiB, p95 frame time ≤33ms on declared target hardware/resolution. Profile cold load, peak randomized demand, route selection, ghost toggling and multiple scenario switches. Reduce materials/textures/props before removing product functionality. No universal FPS or device compatibility claim until measured.

### Dynamic traffic load budget

Initial profiling workload: 300 simultaneously visible civilian vehicles plus the solid ambulance and one render-only ghost; stress at 600 if simulation demand produces that population. These are profiling targets, not achieved capacity or a cap on scientific demand. Use simple shared meshes/materials and instance transforms, with bikes/trucks represented by their own low-poly archetypes. Pool instances and update only active transforms, not rebuild meshes per frame. If the real worst-case population exceeds the target, profile that actual peak and report it. Do not silently delete simulator vehicles or thin benchmark demand to hit a rendering target. At overview scale, explicit aggregate/LOD traffic representations are allowed only if labeled and metrics retain every vehicle; normal view should preserve individual traffic when feasible.

## Verified asset-stage milestone — 2 November 2026

The original procedural pack includes source `.blend` scenes, generators, the canonical graph, nine GLBs and native Blender previews. Nine GLBs total 1,268,584 bytes. City: 14,552 triangles / 15 material primitives; ambulance: 2,378 triangles / 9 primitives. All nine exports have zero Khronos validator errors/warnings; HTTP loading and GLTFLoader parsing passed for 9/9. The cloud browser reports WebGL disabled, so browser pixels, FPS, ghost blending/isolation and dynamic traffic rendering remain release gates. No security settings were changed to bypass this limit.

Graph checks pass for 25 primary intersections, two hospitals and 100 pickup points, including all 200 pickup-to-hospital reachability pairs. This is not SUMO lane, connection, controller or traffic validation. Preserve the exported city root transform, and do not instantiate building rows over the already-baked city buildings. The low-poly targets and scientific validation requirements above remain in force.

Published source and evidence: [asset pack](../assets/README.md), [geometry/export checks](../assets/qa/glb_audit.json), [graph checks](../assets/map/validation_report.json). The archived loader report covers Node parsing; additional browser HTTP/loader smoke checks passed, without WebGL drawing.
