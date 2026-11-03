# Afterlight canonical city manifest

This is the shared geometry source for the expanded city, Blender exports and SUMO importer. The layout is deterministic and original; it uses no external map dataset.

## Reproduce and validate

From the repository root, validate the current manifest:

```powershell
python assets/map/validate_city.py
```

The validator writes `validation_report.json` with the exact input SHA-256. For an intentional map revision in a separate authoring checkout, run `python assets/map/generate_city.py`, validate, then regenerate the Blender city and imported SUMO network from that same manifest. The generator writes the canonical map; it does not update those downstream exports.

Current manifest SHA-256: `f063d28296f395541957fbb89c77cbfa3150a7f76520d5bcf2134d5bc99cb24b`.

## Verified layout

- Local Cartesian **meters**, XY ground plane, Z up, right-hand travel. Bounds: x −1000..1040 m, y −990..1020 m; declared maximum building height 70 m. The 2,040 × 2,010 m footprint is 4.1004 km², exactly four times the original area.
- **81 primary junctions** in a 9 × 9 grid, with 77 signalized nodes. Another 120 service/access/bend/destination nodes bring the graph to 201 nodes.
- 233 physical road corridors, 586 directed graph edges and 1,240 permitted edge transitions. Corridors comprise 144 primary grid streets, 87 subordinate service streets and two hospital driveways.
- 100 curb pickup anchors; two hospitals in opposite diagonal quadrants with graph-connected arrival anchors; 826 buildings and 834 nonoverlapping parcels, including eight parks.
- Shared district palettes, arterial routes, local streets and U-shaped service streets. The enhanced Blender export adds authored roofs, facades, landscaping and distinct hospital landmarks within this layout.

## Consumer contract

- `roads[]`: render each once, using `centerline` and `width_m`. `from_node` / `to_node` identify canonical orientation, not one-way restrictions. All current roads are two-way. Arterials are 18 m wide, two 3.25 m lanes per direction; primary locals 10 m, service streets 8 m, hospital driveways 7 m, one lane per direction. Road width includes spare shoulder/median allocation, not additional lanes. `sidewalk_width_m` is separate.
- `edges[]`: directed simulation topology. Each road is split at access nodes. Edge centerlines remain road-center reference lines; `sim/network.py` offsets right-hand lanes and builds junction interiors and stop lines. Render one surface per road, rather than one per directed edge.
- `connections[]`: legal incoming/outgoing edge transitions, excluding U-turns. These are not swept-path turn curves or phase timing. Hospital arrival nodes are **terminal trip destinations**: arrivals end there; subsequent trips may spawn on their outward edge. A continuous same-vehicle hospital turnaround would need an explicit turnaround/court maneuver before simulation deployment.
- `nodes[]`: stable ids, `[x,y,z]` position, kind, and `signalized` boolean. Main ids `J{row}{column}`. Service nodes `L{column}{row}A/B` are access points; C/D are bends. `stop_line` specifies setback from an edge's destination node and its signal id. The SUMO importer supplies the separate lane-level signal programs.
- `buildings[]`: footprint `center:[x,y]`, `size:[width,depth]`, `height_m`, RGB `color`, `parcel_id`. All footprints are axis aligned. Put cuboid centers at z=height/2. Hospital buildings carry `kind: hospital`.
- `parcels[]`: same footprint center/size contract; `kind` is building, park, or hospital. Building footprints sit inside their parcels. Hospital parcels intentionally contain their access driveways; do not draw grass over the driveway.
- `pickups[]`: ground marker `position`, `road_id`, directed `edge_id`, canonical `curb_side`, `road_fraction`, and `curb_offset_m`. Curb markers lie 1.5 m beyond the asphalt edge. They represent pedestrian pickup anchors, **not vehicle lane positions**. Vehicles approach the associated directed edge; do not drive onto the marker.
- `hospitals[]`: semantic destination id, building reference, graph `destination_node`, `driveway_road_id`, and `driveway_anchor`.
- Stable semantic ids should be retained in exported object/custom properties when practical. Shared materials, instancing/merged static meshes, and texture-free colors support the browser budget.

## QA scope and honest limits

The current [static report](validation_report.json) passes **32 checks**, including unique/referenced ids, the fourfold area and diagonal hospitals, bidirectional permissions, lane-width fit, strong connectivity, legal turns, **all 200 directed pickup-to-hospital routes**, curb/edge consistency, 27.3 m minimum pickup/node distance, nonoverlapping footprints, road clearance, containment and graph nodes at every centerline crossing. [The refresh record](../../docs/validation/static-map-proof-refresh-v1.json) preserves the earlier report's byte identity and confirms that only its stale input checksum needed updating.

This report checks graph and rectangular footprint geometry. Executed [SUMO network qualification](../../docs/validation/expanded-network-qualification.json) and [recording evidence](../../docs/validation/expanded-city-recordings.json) have their own source and audit scopes. Route connectivity does not establish traffic performance or model generalization across all 200 routes.

The manifest's static-city targets are 600,000 triangles and a 20 MB GLB. The current enhanced city has 235,604 triangles and a 14,380,920-byte GLB; the complete shipped product has a separate 50 MB ceiling. See [the asset inventory](../README.md) for source scenes, export hashes and geometry checks. Browser performance is measured separately.

## Documentation / evaluation impact

The three-junction layout remains a small regression fixture. The expanded study uses separately frozen whole-demand groups, regimes and route families; its actual coverage and results belong to [the benchmark protocol](../../docs/BENCHMARK_PROTOCOL.md). Map area and reachable routes describe the available world, not the number of trained or evaluated cases.

The ghost baseline is a **separate nonphysical simulation-result overlay**. It is absent from the graph's physical vehicle population and must not affect queues, collisions, detector counts, routing, or signal actuation. Its saved trajectory may be rendered against the same canonical coordinate system.
