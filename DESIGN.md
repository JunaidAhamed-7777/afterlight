---
version: desktop-v4-identity
colors:
  canvas: '#0A1F44'
  surface: '#183052'
  text: '#F2F7FC'
  muted: '#B0C7D9'
  ambulance: '#FFC067'
  clearance: '#72EAD2'
  ghost: '#85D7FF'
  trafficRed: '#ED8B82'
  brandAmber: '#D98F2A'
  brandTeal: '#2CB2A2'
typography:
  sans:
    fontFamily: 'Inter, Segoe UI, system-ui, sans-serif'
    lineHeight: '1.5'
  mono:
    fontFamily: 'ui-monospace, monospace'
    lineHeight: '1.4'
rounded:
  DEFAULT: '6px'
spacing:
  unit: '4px'
components:
  comparison:
    layout: 'synchronized paired scenes'
  evidence:
    style: 'flat, labeled, tabular'
---

## Overview

A **colorful daylight architectural miniature**, used as a scientific instrument. Cobalt, coral, ochre and teal buildings, green parks and two ivory hospital landmarks give the expanded city character. Dark roads and a warm ambulance keep traffic legible. The memorable signature is **two synchronized futures followed by the aftermath reveal**. Not a neon cyberpunk dashboard, not an unrelated cinematic city, not an ornamental AI landing page.

This is a product surface with one expressive 3D canvas. Evidence controls must remain familiar and quiet. The physical miniature supplies drama; the data supplies credibility. The token owner is `web/src/styles/tokens.css`. Keep semantic values aligned with this document rather than creating competing palette systems. `trafficRed` is reserved for actual controlled-link states, never a universal whole-junction status.

## Colors

Canvas `#0A1F44` and surface `#183052` establish the deep blue instrument shell from the reviewed [Canva identity guide](https://canva.link/plj2l49fb5akdcu). The compact symbol joins perpendicular teal and amber routes with circular terminals. Core mark colors are amber `#D98F2A` and teal `#2CB2A2`; the native SVG is an implementation of the reviewed design, not an exported Canva vector. Text `#F2F7FC` is warm and readable; muted text `#B0C7D9` remains intentionally light. Ambulance amber `#FFC067` is the narrative focal point; clearance mint `#72EAD2` marks the selected corridor. Signal lenses can use traffic-specific colors, but always retain position/labels and accessible text state. Do not encode policy winners only by hue. Measure text/control contrast in the actual rendered UI before claiming WCAG compliance.

## Typography

Self-hosted Inter for controls and the uppercase wordmark, with system monospace and tabular numbers for time, seed and metrics. The original variable WOFF2 is pinned to an official Inter source commit; its full OFL-1.1 license is shipped separately and in the combined notices. No third-party font request is needed. The font is preloaded while the real loading screen owns the workspace. Title 28–36px, body 16px, labels 12–14px; avoid illegible cinematic microtype. English is the initial UI language; fallbacks must not corrupt names or symbols.

## Layout

Desktop: a viewport-bound two-pane instrument. Settings, local generation and evidence scroll independently in the left pane; the right pane retains the 3D city, journey/world labels and playback transport without document scrolling. The city occupies roughly two-thirds of the width. Keyboard users can focus the named settings scroll region or skip directly to the city; scrollbars remain visible and stable. At 720px laptop height, reduce spacing before shrinking labels or moving playback out of view. Small laptop views reduce ornament before shrinking text. Desktop is the only optimization and acceptance target. Preserve existing responsive behavior, but do not spend work on mobile-specific optimization or testing; see `AGENTS.md`. Use a four-pixel spacing unit, 16–24px section gaps and no wall of interchangeable cards.

## Elevation & Depth

Depth belongs to the city. UI panels are largely flat with thin boundaries, no glassmorphism stacks or heavy shadows. Buildings are low-detail masses with warm emissive accents; lights illuminate decision-relevant roads rather than every edge. Keep camera tilt sufficient to distinguish lane queues without hiding signal heads.

## Shapes

Controls use restrained 6px corners; primary controls remain plainly clickable. Buildings and road modules share a disciplined miniature scale. The ambulance silhouette must read from the overview before details are added. Labels never float over the ambulance or obscure stoplines.

## Components

- **Scenario control:** recorded scenario name, seed and provenance; explicit loading/failure state.
- **Comparison canvas:** identical camera/time in both views, policy name anchored consistently.
- **Timeline:** play/pause, elapsed simulated seconds, keyboard-operable scrubber and dispatch/exit markers.
- **Decision inspector:** observed inputs, selected lead, predicted cost and legal transition timing. Clearly distinguish prediction from measurement.
- **Evidence strip:** raw ambulance/civilian outcomes, sample sizes and uncertainty; not animated fabricated counters.
- **Status:** permanent recorded/live distinction, failure/censoring text and fallback links.

Motion follows evidence. Camera transitions reveal the corridor and then queues; do not add perpetual orbiting, excessive bloom or distracting pulse effects. Reduced-motion mode uses fixed camera and no autoplay. See [behavior contract](docs/VIEWER_AND_DEMO.md) for interaction states.

## Do's and Don'ts

Do use original Blender-authored modular assets, coherent lighting, instanced vehicles and honest synchronized traces. Do make the civilian aftermath emotionally visible without inventing causality. Do preserve a readable 2D/table fallback.

Do not use previous car-film assets, unknown-license music, stock emergency footage or decorative fake metrics. Do not spend the deadline on photoreal façades or offline Cycles rendering. A polished demo video captured from the real browser experience remains a core deliverable.

Historical validation through `3060716` belongs to the V3 viewer. Current expanded-city acceptance is recorded separately in [desktop-v4-acceptance.json](docs/validation/desktop-v4-acceptance.json), with exact build bindings and limits. Paused camera sweeps, selected actual rendered stop-line regressions, fixed desktop layout and measured dense playback have passed scoped checks. New source changes require their own affected checks; no blanket accessibility or traffic-safety certification is implied.

## Post-review city and ghost revision

Low-poly is the art direction and performance strategy, not a temporary excuse. Use cuboid multicolored building archetypes, flat/beveled silhouettes and very few shared materials. Cars, trucks and bikes remain simple readable shapes; spend detail on the stylized ambulance hero, not every vehicle. Two hospitals are distinct landmarks. Roughly 100 pickup anchors appear only when selection is active or nearby, avoiding label clutter.

Ghost cyan `#85D7FF` is exclusive to the baseline ambulance. Use transparency/emissive material with a subtle outline or low-cost halo rather than mandatory full-screen bloom. It does not cast meaningful shadows or alter road lighting/signals. The primary scene always remains AFTERLIGHT truth; an alternate inspection view is explicitly baseline. Render-only overlaps are explained, never animated away.

The three-junction corridor is a correctness fixture inside a larger map target, not the visual limit. Zoom-level detail and landmark hierarchy keep the 81-node overview readable. Keep stable overview, deliberate follow mode and reset; no mandatory orbit. Product controls, errors, provenance and route availability are core design, not a demo-only overlay.

## Interactive camera and enhanced geometry

The architectural miniature is now explicitly explorable in true perspective.
Explore 2.5× changes camera magnification, not the physical map scale; Full city
retains the stable fitted overview. X tilt, Y heading and Z view-roll have native
HTML controls and focused-canvas keyboard equivalents. No automatic orbit or
parallax substitute is permitted. Original low-poly traffic assets remain
unchanged and instanced. Enhanced building detail must stay subordinate to
legible traffic and measured browser performance; the 50 MB map allowance is a
ceiling rather than a filesize target. “Reveal streets behind foreground buildings”
starts enabled on every page access. Its in-session opt-out is not persisted.
Foreground transparency is limited to identified buildings in the perspective
view, never a shared-color whole-city fade; Full city remains opaque. See
[3D map and camera contract](docs/CAMERA_AND_3D_MAP.md) for geometry, coordinate
preservation and Omen acceptance gates.

## Desktop usability hierarchy

The first screen offers a clear available action, not absent traffic controls:
explore the city, open a real recording, or use an enabled local runner. Replay
comparison controls/legend appear only with actual evidence. Journey/status text
owns a row outside the canvas; camera controls, compass and errors never compete
for the same corner. Keep seed/policy/lead under a native advanced disclosure,
while the submitted immutable request remains distinguishable from the next run.
Opt-in map markers are actual canonical anchors, with click-versus-drag protection
and complete search/dropdown alternatives. No change to palette, typography or
runtime tokens is needed for this hierarchy.


## Persistent desktop workspace

The desktop shell at widths of 1000px and above occupies the viewport, not the
combined height of settings and evidence. The left pane is the sole long-form
vertical scroller; its footer and evidence stay reachable without moving the
ambulance out of view. The right pane reserves separate rows for world controls,
journey status, the city, comparison legend and playback. Camera controls use an
in-flow dock rather than covering the vehicle; expanded advanced controls must
remain bounded. Preserve native keyboard focus, complete accessible settings,
visible scrollbars and independent horizontal scrolling for dense evidence.
This is an explicit user-requested layout evolution, not a palette or typography
redesign. New layout acceptance requires the pinned desktop Omen cohort.


## November 3 desktop product revision

The owner explicitly requested a complete UI overhaul and brighter, livelier colors and models. This supersedes the older twilight treatment. The city is sunlit and colorful; the interface is a crisp blue frame. The 3D viewport remains the expressive element. Simulation, Results and Settings are three simple sidebar sections rather than one long undifferentiated form. The recording library is first; route selection and raw provenance are secondary disclosures. The public viewer opens a genuine recording when available, without manufacturing traffic.

At 16:9 desktop sizes, a 324–368 px sidebar owns vertical scrolling. The right side owns fixed rows for title/world selection, journey, a flexible 3D view, compact camera dock, comparison legend and playback. A camera-options popover overlays the city instead of resizing the viewport. The boot screen reports actual ready resources, including city geometry and all four vehicle models. A failure offers retry or entry to the accessible workspace.

Token ownership remains Model B: web/src/styles/tokens.css is canonical; this document mirrors accepted values. Canvas/surface/text/muted/ambulance/clearance/ghost map directly to identically named CSS variables. Hover and pressed surfaces are #2C5070 and #355F80; ambulance hover #FFD495. City sky/horizon are #A9D0E6/#D2E7E8. The global scrollbar baseline uses thumb #557A98, track #172D48 and hover #89B2CF. Components consume these semantic variables.

The first successful visit offers five short anchored coachmarks: recording, play, timeline, follow and results. Native modal semantics, contained keyboard focus, Skip/Escape and persistent completion keep it predictable. Settings reopens the guide. The guide pauses playback and leaves the camera/transport rows visible.

Follow Ambulance and Follow Ghost sit immediately after Zoom. The first tracks the visible world's physical ambulance; the second reveals the ordinary ambulance as a cyan overlay in the Afterlight scene. World changes end following; hiding the ghost ends ghost following. Manual camera movement also ends follow. Both controls retain explicit pressed states. Playback speed changes the shared clock at 0.5×, 1×, 2×, 4×, 10× or 20×, preserving the relative recorded physics.

The comparison legend uses transparent renders of the actual ambulance and ghost models. Emergency flashing changes only the authored roof-light material, using wall time at 2.5 color changes per second independently of playback speed. Paused and reduced-motion views use steady blue; the ghost remains cyan. No invented vehicle motion, extra roof geometry or scene-wide flashing is introduced.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Select/Listbox | Native HTML select in App and LocalGeneration | docs/VIEWER_AND_DEMO.md | Native; operating-system popup appearance and geometry accepted | Desktop product acceptance, keyboard and popup inspection |
| Scrollbar | Global web/src/styles/app.css baseline | DESIGN.md | Stable left gutter; horizontal overflow for dense evidence | Desktop product acceptance and computed styles |
| Loading | App boot screen, CityView resource callbacks, recording loader | docs/VIEWER_AND_DEMO.md | Initial resources; recording; inline recovery | Real network loading/failure browser tests |
| Forms | LocalGeneration and generation.ts | API job/idempotency contract | Immutable submitted job vs next request | API and generation tests |
| Feedback | Inline status/error regions owned by the active operation | docs/VIEWER_AND_DEMO.md | Informational/status/error | Failure/recovery browser tests |

Local pickup filtering is immediate and transient. The clear button resets the query and returns focus to search. Long-lived request state remains owned by LocalGeneration; changing sidebar sections preserves it. Native controls preserve keyboard interaction and actual source outcomes remain inspectable without WebGL.

## Journey editing and algorithm evidence

The journey disclosure is a visible control surface with a labeled header and directional indicator. Selecting a recording locks and blurs the complete pickup/search/hospital/map-selection field group, including during loading or a recording error. The unblurred **Leave recording & explore** action stays above that group and returns focus to pickup search after unlocking. Disabled native fieldset semantics preserve keyboard behavior; blur alone never enforces the lock.

Results separates **This run**, **Study** and **Algorithm**. Algorithm explains the selected recording's route calculation and display using its saved evidence and recognized source hashes. Show the solid and ordinary/ghost responses as separate physical worlds sharing the saved route where that is what the source records. Distinguish the distance-based route objective, lane-geometry reference length, signal-priority timing and measured journey duration. Fold exact edges and source details beneath a concise process explanation. Unknown source versions and missing route details remain explicit.

## Identity implementation after first hosting

The first public Vercel deployment preceded Canva creation, as requested. The eight-page editable guide supplies the route symbol, navy shell, core amber/teal and Inter typography. Its generated contact and unsupported simulation claim were corrected; ghost cyan identifies the ordinary-world ambulance. The header and loading screen reuse one native SVG mark, with the same symbol in the favicon. Real loading progress and error recovery remain functional.

`web/src/styles/tokens.css` remains the runtime authority. The accessible interface tints `#FFC067` and `#72EAD2` retain their existing action/corridor roles; these are brighter variants of the core identity colors for small text and controls. The tested emergency roof lights, actual signal lenses and ghost material keep their rendering colors. Flat daylight sky is deliberate: the paused scene must remain pixel-stable. Original colorful city models are preserved.
