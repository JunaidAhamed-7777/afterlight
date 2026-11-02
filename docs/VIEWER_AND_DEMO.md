# Viewer behavior and demo direction

## One primary workflow

Select a supported pickup/hospital and available scenario → view solid AFTERLIGHT ambulance with baseline ghost → play/scrub on the same clock → inspect either world and dispatch decision → inspect aftermath → open benchmark evidence. For static mode, offer only combinations with exported runs; do not imply arbitrary selection launches a new simulation.

The screen is a product instrument, not a marketing landing page. A short title and one sentence explain the experiment; the city takes priority. Keep a permanent **Recorded simulation** badge, seed and policy labels. A local live runner, if implemented, gets a different explicit mode and progress state.

## Behavior contract

- The ghost overlay and optional separate views share one simulated clock, camera transform and playback speed. Pausing or scrubbing updates both.
- Scenario changes reset playback and preserve clearly selected policies; never mix metrics from a previous run with new geometry.
- A loading state names the requested scenario. Network failure offers retry and an accessible static summary, never fake data.
- Invalid/missing trace displays an error with no benchmark values presented as valid.
- A completed run keeps the results visible; a noncompleted ambulance is labeled, not animated out of view.
- Keyboard controls support play/pause and the timeline without trapping focus; buttons have visible focus and meaningful labels.
- Colors are accompanied by labels/shape cues. Charts and metrics remain text-readable without WebGL.
- Reduced motion disables autoplay/cinematic camera movement; manual scrubbing remains.
- On small screens use a synchronized A/B toggle with the same clock and camera, preserving policy labels and paired metrics without rendering two unreadably small cities.

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

Capture desktop and narrow-screen screenshots, a keyboard walkthrough, reduced-motion behavior, trace-load failure, WebGL fallback and a synchronized seek. Check that counters exactly match exported metrics and that turning vehicles remain on roads. An attractive screenshot alone does not prove a working viewer.

## Product-level ghost and scenario requirements

The default city shows active AFTERLIGHT civilians/signals and a solid detailed ambulance. The light-blue glowing baseline ghost is only a presentation of a second world’s ambulance trace. Permanent legend: “Solid: AFTERLIGHT world · Ghost: baseline, separate traffic world.” Offer ghost visibility/opacity control, inspect-baseline view and reset camera. Use a shared absolute clock, never normalized completion animations. A short explanatory tooltip addresses apparent ghost overlaps with active traffic/signals. Keep glow restrained and inexpensive; opacity must not obscure the active ambulance or imply the ghost controls traffic.

Pickup/hospital selection is backed by authoritative graph IDs and accessible searchable lists, not canvas-only clicking. Clearly show which of roughly 100 anchors and two hospitals are supported by a loaded run. Validate route availability; explain unavailable combinations. Local live mode can start only implemented, validated routes; public replay mode selects existing captures. Changing selection resets the paired run deliberately and confirms the active scenario, not stale metrics.

Loading exposes progress where known, cancellation where supported, retry and an error reason. Never leave an infinite blank canvas. A failed or stalled live world pauses the pair with a clear reconnect/retry choice. Browser context loss presents a recoverable fallback/results table. Keyboard focus stays visible after dialogs/selections, touch targets remain usable, reduced motion disables auto-follow and glow animation. Mobile uses one active view plus baseline toggle rather than illegibly tiny comparisons.

The user should be able to answer: What is running? Which pickup/hospital and seed? Is this recorded or live? What did each ambulance actually do? How much did civilians wait? What is supported and what failed? These are product acceptance questions, not optional presentation polish.
