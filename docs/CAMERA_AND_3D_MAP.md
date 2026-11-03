# Interactive 3D city

## Geometry, not parallax

The city, roads, buildings, cars, trucks, bikes and ambulance are actual glTF mesh
geometry. No camera-facing photographs or parallax layers stand in for those
objects. The enhanced map adds modeled window bays, architectural ledges and
small rooftop volumes to the original building masses. Hospitals retain their
original modeled details. Road slabs, sidewalks, parks and canonical road
coordinates are preserved.

`assets/exports/city_enhanced.glb` is the interactive map. Its companion manifest
records its exact bytes, hashes, original source, per-building visual bounds and
187 stable building IDs. `assets/afterlight_city_enhanced.blend` is editable source;
`assets/src/enhance_city.py` reproduces the enhancement from the original Blender
city without regenerating streets. Original map and vehicle assets remain in the
repository. The 25 MB map allowance is a ceiling, not a target: this export is
approximately 4.11 MB. Cars, trucks and bikes remain the original tiny low-poly
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
headed browser checks on Omen. Capture overview, perspective, mobile and a real
foreground-occlusion witness; record actual renderer draw calls and frame times
rather than inferring speed from file size. No fabricated traffic recording or
benchmark is bundled to make the map appear busy.
