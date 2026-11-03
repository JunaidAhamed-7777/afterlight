# Viewer behavior and demo

## First use

The public viewer opens an available genuine recording. The Simulation pane
names its journey, seed and physical policy; **Play** advances both independent
worlds on one absolute clock. Playback speeds run from 0.5× to 20×, including
10× and 20× for longer journeys. **Follow Ambulance** frames the solid ambulance
in the inspected world. **Follow Ghost** opens Afterlight with the ordinary-world
ghost visible and follows that trajectory. Subsequent zoom/orbit adjustments
are preserved. Switching **Afterlight/Ordinary** inspects that world's own traffic
and signals and releases follow. Open **Results** for whole-run outcomes.

The left Simulation/Results/Settings pane scrolls independently. The right city,
world selection, camera dock and playback stay visible in a normal 16:9 desktop
window. With an empty catalog the same product offers city exploration. Public
mode plays published captures; the explicitly enabled local runner can generate
a new pair and then open its completed recording.

A short first-visit walkthrough introduces recording selection, playback,
seeking, follow and results. Finishing or skipping is stored locally; Settings
can reopen it. The legend pairs actual model thumbnails with text labels.

## Recorded evidence

“Recorded simulation” remains visible during playback. The two current public
city pairs use a 3 s all-red clearance and retain every 0.5 s SUMO integration
boundary through 900 s. Gzip changes
only transport size. Recordings, source hashes, original metrics and audit scope
are documented in [public recording evidence](validation/expanded-city-recordings.json).
These exploratory examples do not establish aggregate or held-out policy benefit.
Their measured results include civilian cost as well as ambulance time:

- Cross-city, fixed 20 s lead: ambulance 601.0 → 473.0 s; mean civilian excess
  travel time 111.49 → 113.68 s (Ordinary → Afterlight). All 398 civilians finished.
- Westhaven, analytical 0 s lead: ambulance 426.5 → 322.5 s; mean civilian excess
  travel time 106.85 → 107.98 s. All 426 civilians finished.

All four worlds reported zero collisions and teleports. The source-bound
[presentation review](validation/expanded-city-presentation.json) found no red or
unresolved classifications among 9,839 geometry-eligible stop-line crossings.
That scoped presentation check is separate from raw physics audits and does not
certify universal traffic safety.

The solid ambulance, civilians, queues and movement arrows belong to the inspected
world. The optional cyan ghost is the actual baseline ambulance on the same clock.
Its own cars and lamps exist in the Ordinary view; apparent overlap with active
traffic is explained by the “Two traffic worlds” disclosure. The ghost is never
inserted into the active simulator or used to trigger priority.

Signals show individual controlled movements using imported lane geometry.
Exact recorded control-event boundaries are used only when their reconstructed
states match every saved lamp state; legacy recordings retain sampled states
when that evidence is incomplete. Metrics are fixed whole-run measurements.
Only display poses interpolate between adjacent real samples. New/removed IDs
and teleports retain explicit lifecycle behavior.

## Loading and recovery

The initial loading screen reports completed resources. Dense recording fetch,
gzip decode, checksum/schema validation and parsing run in a worker. The workspace
stays responsive while a requested recording loads; cancellation terminates that
worker. Failed or mismatched recordings offer retry and clear stale outcomes.
A fixture or another-map recording opens its HTML evidence without placing those
vehicles on the current city.

Model requests have a 60 s deadline and are aborted when the renderer is replaced.
Recording requests have a 30 s fetch deadline. Graphics failure shows a labeled
Blender preview and retry while HTML results remain available. A local-generation
failure preserves exact job identity; an uncertain POST is recovered with GET
before an explicit retry using the same immutable request ID/settings. Closing
the page does not cancel a simulator process.

## Interaction contract

- Pause and scrub update both worlds at the same absolute time and speed.
- Changing recordings clears earlier traffic, errors and outcomes.
- Journey/status text has a row outside the canvas; controls do not cover it.
- Leave a recording explicitly to change its journey. Map picking distinguishes
  a click from a drag and has complete search/dropdown alternatives.
- Active/recovering/uncertain local jobs lock map picking. Saved parameters remain
  separate from a proposed next run.
- Camera shortcuts act only on the focused map. Native controls have meaningful
  labels and visible focus. Tab can leave the map.
- Reduced motion disables continuous follow; there is no automatic playback.
- Building cutaway is optional and off by default. Logarithmic depth keeps thin
  authored road/facade layers stable during perspective orbit.
- Desktop is the acceptance target. Preserve responsive behavior without adding
  mobile-specific optimization or default mobile checks.

The camera contract and exact coordinate behavior are in
[Desktop 3D city](CAMERA_AND_3D_MAP.md). The total shipped-asset ceiling is 50 MB;
decoded recording memory is a separately measured desktop cost.

## Demo capture outline

This two-minute outline is an editorial option, not a verified contest limit.

| Time | Show |
|---|---|
| 0:00–0:15 | A real ambulance approaching a queue, with the simulation label. |
| 0:15–0:50 | Same demand, separate worlds: observed inputs, chosen lead and legal signal transition. |
| 0:50–1:20 | Civilian queues after the ambulance finishes, using the common drain window. |
| 1:20–1:45 | The actual frozen study result and sample count, or a clear statement that it is not released. |
| 1:45–2:00 | Limitations, reproducible source and local execution. |

Capture actual browser playback and measured outcomes. Caption narration; optional
music requires reuse rights. Do not turn one favorable demonstration into an
aggregate claim or replace an unfavorable measured result.

## Acceptance and historical records

Current checks cover desktop layouts, keyboard use, reduced motion, cancellation,
worker/graphics recovery, synchronized seeking and actual render-buffer poses.
The dense regression additionally tests the stopped civilians that crossed red
in the former coarse presentation. Review screenshots at several tilts/yaws;
a single attractive frame does not establish a stable product.

Historical: earlier camera/cutaway/usability checks passed through `7ef8ffe`, and
`3060716` accepted scoped replay/ghost matrices and corrected tyre contact on the
smaller city. At the November 3 owner halt, the later desktop redesign was still
unbuilt/untested. Those entries remain true for their recorded source cohorts;
new product acceptance belongs to the current build and captures. See the
[chronological Omen log](validation/OMEN_LOG.md) for those earlier outcomes.
