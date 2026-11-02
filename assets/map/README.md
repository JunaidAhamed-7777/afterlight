# Afterlight canonical city manifest

Original deterministic procedural layout; no external map datasets, models, textures, or paid services. This directory is local staging, not a public repository publication.

## Reproduce and validate

```sh
python generate_city.py
python validate_city.py
```

`city_manifest.json` is the single source of geometry for Blender and the future simulation importer. `validation_report.json` records checks against its SHA-256. Do not hand-edit a second road layout in Blender.

## Verified layout

- Local Cartesian **meters**, XY ground plane, Z up, right-hand travel. Origin is the city center, not a geographic coordinate. Bounds: x −500..520 m, y −495..510 m (1.0251 km²); buildings at most 48 m tall.
- **25 primary grid junctions**, irregular spacing. 32 other graph nodes comprise 14 service-street access points, 14 service bends, two hospital driveway access points, and two hospital terminal destinations. These are not 57 primary crossroads.
- 63 physical road corridors, 158 directed graph edges, 312 permitted edge transitions. 40 primary network road corridors, 21 subordinate service-road corridors, two hospital driveways.
- 100 curb pickup anchors; two hospitals with graph-connected arrival anchors; 187 original cuboid buildings; 189 nonoverlapping parcels including two parks.
- Four district labels/palette families. Broad connected arterial routes, quieter local streets, and small U-shaped service streets keep the larger city legible without uniform checkerboard spacing.

## Consumer contract

- `roads[]`: render each once, using `centerline` and `width_m`. `from_node` / `to_node` identify canonical orientation, not one-way restrictions. All current roads are two-way. Arterials are 18 m wide, two 3.25 m lanes per direction; primary locals 10 m, service streets 8 m, hospital driveways 7 m, one lane per direction. Road width includes spare shoulder/median allocation, not additional lanes. `sidewalk_width_m` is separate.
- `edges[]`: directed simulation topology. Each road is split at access nodes. Edge centerlines remain road-center reference lines; a future importer must offset individual right-hand lanes, build junction interiors, and clip stop lines. Do not render one road per edge or independently reshape the edges.
- `connections[]`: legal incoming/outgoing edge transitions, excluding U-turns. These are not swept-path turn curves or phase timing. Hospital arrival nodes are **terminal trip destinations**: arrivals end there; subsequent trips may spawn on their outward edge. A continuous same-vehicle hospital turnaround would need an explicit turnaround/court maneuver before simulation deployment.
- `nodes[]`: stable ids, `[x,y,z]` position, kind, and `signalized` boolean. Main ids `J{row}{column}`. Service nodes `L{column}{row}A/B` are access points; C/D are bends. `stop_line` on an edge specifies setback from its destination node and its signal id, where applicable. Signal phase programs are not supplied.
- `buildings[]`: footprint `center:[x,y]`, `size:[width,depth]`, `height_m`, RGB `color`, `parcel_id`. All footprints are axis aligned. Put cuboid centers at z=height/2. Hospital buildings carry `kind: hospital`.
- `parcels[]`: same footprint center/size contract; `kind` is building, park, or hospital. Building footprints sit inside their parcels. Hospital parcels intentionally contain their access driveways; do not draw grass over the driveway.
- `pickups[]`: ground marker `position`, `road_id`, directed `edge_id`, canonical `curb_side`, `road_fraction`, and `curb_offset_m`. Curb markers lie 1.5 m beyond the asphalt edge. They represent pedestrian pickup anchors, **not vehicle lane positions**. Vehicles approach the associated directed edge; do not drive onto the marker.
- `hospitals[]`: semantic destination id, building reference, graph `destination_node`, `driveway_road_id`, and `driveway_anchor`.
- Stable semantic ids should be retained in exported object/custom properties when practical. Shared materials, instancing/merged static meshes, and texture-free colors support the browser budget.

## QA scope and honest limits

30 checks currently pass, including unique/referenced ids; bidirectional permissions; lane-width fit; strong node connectivity; legal turns; **all 200 directed pickup-to-hospital routes including permitted turn transitions**; curb/edge consistency; pickups outside intersections (minimum node distance 27.3 m), buildings, and road interiors; building/parcel nonoverlap; road clearance; containment; bounds; and graph nodes at every geometric centerline crossing.

The validator checks this graph and rectangular footprint geometry. It does **not** claim SUMO import, lane-level junction geometry, swept-path feasibility, signal-controller correctness, traffic dynamics, AI performance, or browser performance. `sumo` and `netconvert` were not available in this workspace. Before integration, import into SUMO, inspect lane connections and hospital maneuvers, and reconcile any required geometry change back into this source manifest before re-exporting art. No art/network divergence is accepted merely because both render.

Static city targets: **<150,000 triangles** and **<10 MB GLB**. These are budgets, not measured export results; the Blender worker must report actual exported counts/bytes and visual QA.

## Documentation / evaluation impact

The earlier three-junction layout is a **small regression fixture**, not the entire city or a claim that a three-junction benchmark demonstrates city-scale benefit. Start controlled corridor experiments within the larger city, preserving matched seeds, demand, incidents, and signal policies. Add held-out routes, pickup/hospital pairs, demand levels, and traffic scenarios before drawing city-wide conclusions. More map area adds route diversity and visual context; it does not automatically make experiments feasible, valid, or generalizable.

The ghost baseline is a **separate nonphysical simulation-result overlay**. It is absent from the graph's physical vehicle population and must not affect queues, collisions, detector counts, routing, or signal actuation. Its saved trajectory may be rendered against the same canonical coordinate system.
