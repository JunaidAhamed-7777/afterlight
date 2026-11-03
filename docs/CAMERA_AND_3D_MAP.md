# Interactive 3D city

## Geometry, not parallax

The city, roads, buildings, cars, trucks, bikes and ambulance are actual glTF mesh
geometry. No camera-facing photographs or parallax layers stand in for those
objects. The enhanced map adds modeled window bays, architectural ledges and
small rooftop volumes to the original building masses. Hospitals retain their
original modeled details, with structural canopy supports and roof-edge framing. Road slabs, sidewalks, parks and canonical road
coordinates are preserved.

`assets/exports/city_enhanced.glb` is the interactive map. Its companion manifest
records its exact bytes, hashes, original source, per-building visual bounds and
187 stable building IDs. `assets/afterlight_city_enhanced.blend` is editable source;
`assets/src/enhance_city.py` reproduces the enhancement from the original Blender
city without regenerating streets. Original map and vehicle assets remain in the
repository. The 25 MB map allowance is a ceiling, not a target: this export is
approximately 4.44 MB. Cars, trucks and bikes remain the original tiny low-poly
models, rendered through the existing instanced vehicle layer.

## Camera contract

**Explore 2.5×** uses a real perspective camera and a closer, lower-angle view.
The factor describes camera target-plane magnification relative to the fitted
full-city view; it does not multiply physical road lengths or simulation
coordinates. Near and far objects therefore have genuine perspective depth,
not uniform screen scaling. **Full city** restores the padded orthographic
inspection overview, including on narrow screens.

- Drag to orbit; right-drag or the explicit Pan option pans.
- Scroll/pinch or keyboard `+`/`-` zooms.
- Native HTML buttons provide X tilt, Y turn and Z view-roll. These are camera
  controls, not rotations of the canonical world. `X`, `Y`, `Z` work when the
  canvas has focus; Shift reverses each direction.
- `0` or Reset restores Full city and clears roll. Tab leaves the canvas.
- Camera controls never change the shared simulation clock or either world's
  traffic, signals or physical vehicle positions.

No automatic decorative orbit is introduced. Reduced-motion preferences remain
in force for playback/follow behavior; direct user camera actions remain usable.

## Selective obstruction transparency

Only explicitly identified building nodes can become transparent. Ground,
roads, trees, signals and vehicles are excluded, even when they share the same
material color. The original city root translation is retained exactly once.
Building geometry is consolidated into shared-material render batches while a
small per-building opacity texture controls stable screen-door transparency.
This avoids making all buildings transparent through a shared material and
avoids adding a draw call for every building part.

The effect is optional and visual only. Foreground blockers on the camera's
focus corridor are revealed; unrelated buildings retain their normal appearance.
Turning the option off or returning to Full city restores opaque buildings.
Actual browser rendering, close-range geometry, roll/pan interaction and
occlusion witnesses must be inspected on Omen before acceptance.

## Evidence and validation

The reference URL supplied for interaction direction was not accessible through
the available web reader. This implementation follows the explicit request;
it does not claim a verified visual match to that site.

This revision has cloud build/export evidence only until its pinned Omen tests
are recorded. It is not evidence of loaded-traffic frame rate or SUMO accuracy.
The previous browser acceptance belongs to its older source/build checkpoint.
Run asset structure tests, frontend unit tests, exact preview verification and
headed browser checks on Omen. Capture desktop overview, perspective, resized desktop windows and a real
foreground-occlusion witness; record actual renderer draw calls and frame times
rather than inferring speed from file size. No fabricated traffic recording or
benchmark is bundled to make the map appear busy.

## Desktop-first, state-aware controls

Desktop is the sole optimization/acceptance target; see root `AGENTS.md`. Existing
responsive behavior remains, but mobile-specific browser checks are opt-in and
are not part of the default acceptance run. Keyboard access and reduced-motion
settings remain essential desktop behaviors.

The selected journey/status has its own row outside the canvas, so the camera
controls cannot cover it. With no recording, the interface offers city exploration
and (in local mode) generation rather than inactive playback and ghost controls.
Comparison controls appear only when a real recording is loaded. Experimental
seed/policy/lead settings live under a native Advanced disclosure; saved-job
recovery keeps the exact submitted request identity and parameters.

## Choosing a journey directly on the map

Choose **pickup on map** or **hospital on map** beside the journey dropdowns.
Only the existing canonical curb or driveway anchors appear; no freehand road
coordinates, synthetic route nodes or vehicle picking are introduced. Markers
use one small instanced geometry layer. Their position is converted from the
same canonical coordinates as the city, and picking uses the actual rendered
perspective/orthographic camera, including roll.

A click commits the named location; dragging still moves the camera and never
changes the journey. Escape or Cancel leaves the journey unchanged and restores
focus to its initiating button. Search and native dropdowns remain the keyboard
alternative. Markers disappear outside selection mode; hover names are not
repeated live announcements.

Selection waits for a successful first map render. It is unavailable while a
recording is loading/playing or a generation request is active, recovering or
uncertain. Leave the recording explicitly to choose a new journey. Saved job
parameters remain immutable even if the next-journey dropdowns change. The map
selection protocol harness uses intercepted, explicitly synthetic API responses;
it is not a genuine traffic run or public recording.

## Geometry revision v3

V3 gives the 185 small rooftop service volumes a one-segment edge chamfer,
producing actual directional-light facets without textures or subdivision.
Both hospitals gain two canopy support columns, a shallow front fascia and
upper-roof perimeter framing; the original roof H stays unobstructed. Original
source faces, canonical roads, vehicle meshes and the 187 building IDs remain
unchanged. New detail uses the existing 15 shared materials.

The exported GLB is 4,439,048 bytes with 84,540 authored triangles. These are
export inventory figures, not browser performance measurements. V2's actual
Omen renderer counters must not be attributed to V3. Close-range appearance,
cutaway correctness and loaded-traffic performance require new Omen acceptance.
