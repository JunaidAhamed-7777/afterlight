# Desktop 3D city and camera

## Current geometry

The interactive map is `assets/exports/city_enhanced.glb`: original mesh geometry
for a 2,040 × 2,010 m district, four times the original area. It has 81 primary
junctions, 826 addressable buildings, eight landscaped parks and two distinct
hospitals in diagonal quadrants. Cars, bikes, trucks and the ambulance use actual
GLB geometry with runtime instancing. Traffic follows exported SUMO poses.

The city export is 14,380,920 bytes and 235,604 triangles. Its companion manifest
binds the canonical map, generator, GLB and per-building bounds. Editable source
is `assets/afterlight_city_expanded.blend`; `assets/src/generate_city_v4.py`
reproduces it through the pinned Blender MCP bridge. Original prototype scenes
and vehicle GLBs remain preserved. The project-wide shipped-asset ceiling is
50,000,000 bytes, including compressed recordings; it is not a target file size.

Blender XY/Z-up maps once to browser `[x,z,-y]`. Preserve the authored city root
translation. Vehicles alone are centered around their measured footprint and
scaled to recorded length/width. SUMO front-bumper coordinates determine the
model nose. Lowest tyre geometry rests at recorded elevation plus the authored
0.18 m road top. Visual hospital plaza slabs end at 0.14 m, leaving actual depth
separation from their driveways.

## Desktop workspace

Simulation, Results and Settings share an independently scrolling left pane.
The right pane retains journey/world labels, city, camera dock and playback in
normal 16:9 desktop windows. Desktop resizing, keyboard use and reduced motion
are acceptance requirements. Mobile-specific optimization and tests remain
outside the target; existing responsive behavior is preserved.

## Camera controls

- **Explore** starts at 2.5× target-plane magnification with genuine perspective.
- **Full city**, the overview button or focused-canvas `0` fits the complete city
  with padding and clears roll.
- Drag to orbit. Right-drag, arrow keys or the Pan option move the camera target.
- Scroll or `+`/`−` zoom; native zoom buttons are also available.
- X tilt, Y heading and Z view-roll have native buttons and focused-canvas
  keyboard shortcuts. Shift reverses the rotation. Tab leaves the map.
- **Follow Ambulance** frames the solid ambulance in the inspected world.
  **Follow Ghost** switches to Afterlight, enables the cyan ordinary-world
  ambulance and follows it. Starting either target uses at least 12× target-plane
  zoom; continued tracking preserves subsequent zoom, orbit and roll. Deliberate
  pan, Explore or Full city releases follow.

Both inspected worlds retain the same comparison camera and absolute clock.
Changing the inspected world releases follow; the camera remains in place.
Seeking or changing recordings handles discontinuities without a stale flight
across the map; after
the last observed ambulance pose, the camera can hold that endpoint. This camera
behavior does not insert a vehicle after its recorded removal. Reduced motion
disables continuous follow; deliberate camera actions and playback remain usable.
The legend uses small transparent renders of the actual ambulance and cyan ghost,
with text labels; these thumbnails do not substitute for scene geometry.

Logarithmic depth keeps kilometre-scale perspective compatible with thin road,
roof and facade layers. Static buildings cast shared shadows once; ground receives
them. Balanced and High change pixel ratio/shadow resolution. These settings do
not rescale the city or alter simulation coordinates.

## Foreground building reveal

“Reveal streets behind foreground buildings” is **on by default on every page
access**. Camera options can turn it off for the current visit; this opt-out is
not persisted across page loads. Identified building
nodes share material batches and a per-building opacity mask. The effect uses
screen-door transparency and changes with the view direction; roads, trees,
vehicles and signals stay outside that mask. Turning it off restores solid
buildings. Full city remains opaque.

## Choosing a journey

Leave a recording before selecting a new pickup/hospital. The map buttons show
actual canonical anchors; a click commits the named anchor, while dragging moves
the camera. Escape/Cancel preserves the journey and restores the initiating
button's focus. Search and native dropdowns provide keyboard alternatives.
Selectable anchor clouds appear only in pick mode; selected-journey markers can
remain visible. Picking waits for a successful render and is locked during
loaded/loading recordings and active/recovering/uncertain local requests.
Submitted job parameters remain immutable when next-journey dropdowns change.

## Verification scope

[Binary geometry acceptance](../assets/qa/city_expanded_acceptance.json) records
nine checks, a byte-identical repeated Blender MCP build and the plaza-depth
regression. [Khronos validation](../assets/qa/city_expanded_gltf_audit.json) has
zero errors, warnings or informational issues for the current asset. These do
not measure browser speed or certify every possible camera/GPU combination.

Current headed desktop acceptance includes actual instance-buffer comparisons,
world/ghost isolation, close and overview cameras, keyboard actions, failure
recovery and multi-angle paused/repeat captures. Run the current product harness
from [web/README.md](../web/README.md). Keep the served-build manifest and source
identity with each result; compilation and file size alone do not establish
visual quality or frame time.

## Historical V3 checkpoint

V3 was the earlier 187-building enhancement: 4,439,048 bytes and 84,540 triangles,
with facade bays, ledges, chamfered rooftop service volumes and hospital canopy
supports. Its source is `assets/afterlight_city_enhanced.blend` and
`assets/src/enhance_city.py`. The old 25 MB allowance and original 25-primary-node
map belonged to that scope. Earlier accepted measurements through `3060716`
remain specific to those source/build bytes. They do not validate the later
826-building city, depth fix or dense public recordings.
