# Viewer behavior and demo direction

## One primary workflow

Start with one clear next action: explore the real 3D city, open an available
paired recording, or generate a run through an enabled local runner. An empty
catalog explains that no traffic is being simulated; it does not show fictional
ambulances or a wall of disabled comparison controls. Public mode permits map
inspection but only exported runs can be played.

With a recording: inspect the solid AFTERLIGHT ambulance and separate-world
ghost, play/scrub their common clock, inspect either world and dispatch decision,
then inspect aftermath and study evidence. Keep **Recorded simulation**, seed
and physical policy explicit. Local generation shows real job status and offers
its completed recording; it is not a live-streaming traffic mode.

Journey/status text owns a row outside the canvas. Camera controls, compass and
errors must not obscure it. Native search/dropdowns remain complete alternatives
to opt-in map selection. The map buttons require a ready renderer, show actual
canonical anchors, suppress selection after dragging, and offer Escape/Cancel.
A loaded recording requires an explicit new-journey action before map picking;
active/recovering/uncertain jobs lock map picking without mutating saved requests.
Advanced seed/policy/lead settings are disclosed below the simple generation
workflow, with the immutable submitted settings clearly distinguished from a
proposed next run.

## Behavior contract

- The ghost overlay and optional separate views share one simulated clock, camera transform and playback speed. Pausing or scrubbing updates both.
- Scenario changes reset playback and preserve clearly selected policies; never mix metrics from a previous run with new geometry.
- A loading state names the requested scenario. Network failure offers retry and an accessible static summary, never fake data.
- Invalid/missing trace displays an error with no benchmark values presented as valid.
- A completed run keeps the results visible; a noncompleted ambulance is labeled, not animated out of view.
- Keyboard controls support play/pause and the timeline without trapping focus; buttons have visible focus and meaningful labels.
- Colors are accompanied by labels/shape cues. Charts and metrics remain text-readable without WebGL.
- Reduced motion disables autoplay/cinematic camera movement; manual scrubbing remains.
- Desktop is the current acceptance target. Preserve existing responsive behavior, but do not add mobile-specific optimization/testing without a new owner request.

## Two-minute editorial storyboard

These timings are a presentation choice, not a verified contest video limit.

| Time | Evidence and image |
|---|---|
| 0:00–0:15 | Ambulance meets a queue. One clear problem statement and “simulation” label. |
| 0:15–0:50 | Same demand, two futures. Show the selected lead, observed queue inputs and legal phase change. |
| 0:50–1:20 | Pull the camera back after ambulance exit. Reveal civilian queue debt and recovery, not a victory freeze-frame. |
| 1:20–1:45 | Held-out benchmark plus no-ML ablation; show actual sample count, intervals and tradeoff. |
| 1:45–2:00 | Stress case/limitations, reproducible repository and local execution evidence. |

Record real playback and real metrics. Use overlays to clarify, not conceal missing behavior. A cinematic intro must not consume the time needed to demonstrate technical substance. Caption spoken content. Music is optional and only with verified reuse rights.

## Acceptance evidence

Capture desktop screenshots at normal window sizes, a keyboard walkthrough, reduced-motion behavior, trace-load failure, WebGL fallback and a synchronized seek. Check that counters exactly match exported metrics and that turning vehicles remain on roads. An attractive screenshot alone does not prove a working viewer.

## Product-level ghost and scenario requirements

When a genuine city recording is loaded, its default view shows active AFTERLIGHT civilians/signals and a solid detailed ambulance. The light-blue glowing baseline ghost is only a presentation of a second world’s ambulance trace. While displaying that comparison, keep the legend: “Solid: AFTERLIGHT world · Ghost: baseline, separate traffic world.” Do not display a traffic legend in asset-only exploration. Offer ghost visibility/opacity control, inspect-baseline view and reset camera. Use a shared absolute clock, never normalized completion animations. A short explanatory tooltip addresses apparent ghost overlaps with active traffic/signals. Keep glow restrained and inexpensive; opacity must not obscure the active ambulance or imply the ghost controls traffic.

Pickup/hospital selection is backed by authoritative graph IDs and accessible searchable lists, not canvas-only clicking. Clearly show which of roughly 100 anchors and two hospitals are supported by a loaded run. Validate route availability; explain unavailable combinations. The explicitly enabled local runner validates requested canonical routes; accepted traffic outcomes still require real rollout/audit. Public replay mode selects existing captures. Changing selection resets the paired run deliberately and confirms the active scenario, not stale metrics.

Loading exposes progress where known, cancellation where supported, retry and an error reason. Never leave an infinite blank canvas. A local-generation failure preserves its job identity and explains recovery; an uncertain response never silently submits a duplicate job. Browser context loss presents a recoverable fallback/results table. Keyboard focus stays visible after dialogs/selections, touch targets remain usable, reduced motion disables auto-follow and glow animation. Desktop world switching preserves the common clock and comparison camera.

The user should be able to answer: What is running? Which pickup/hospital and seed? Is this recorded or live? What did each ambulance actually do? How much did civilians wait? What is supported and what failed? These are product acceptance questions, not optional presentation polish.

## Camera and acceptance status

Explore 2.5× uses actual perspective, not parallax; Full city restores the fitted
overview. X/Y/Z controls mean tilt, heading and view-roll. Manual input never
retimes replay. Foreground transparency affects identified building geometry,
not roads, traffic state or a shared whole-city material. The 25 MB map ceiling
and low-poly vehicle strategy remain performance constraints.

Earlier desktop camera/cutaway/usability checks passed on Omen through `7ef8ffe`.
V3 geometry, map picking and later source changes await a new pinned cohort. A
static review or a successful build is not screenshot, shader, performance or
traffic acceptance. No accepted paired replay, pilot or learned result exists.
The planned offline learned-selection bridge must be labeled as selection of a
recorded fixed-lead candidate, with study conclusions separate from one replay.
