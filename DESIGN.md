---
version: alpha
colors:
  canvas: '#101C2B'
  surface: '#1C2C40'
  text: '#F4F1E8'
  muted: '#B4C1CE'
  ambulance: '#FFB85C'
  clearance: '#78D9CB'
  ghost: '#87D7FF'
typography:
  sans:
    fontFamily: 'system-ui, sans-serif'
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

An **architectural miniature at twilight**, used as a scientific instrument. Warm building windows and a luminous ambulance make a compact 20–25-junction city feel distinctive and legible; navy roads and restrained geometry keep queues readable. The memorable signature is **two synchronized futures followed by the aftermath reveal**. Not a neon cyberpunk dashboard, not an unrelated cinematic city, not an ornamental AI landing page.

This is a product surface with one expressive 3D canvas. Evidence controls must remain familiar and quiet. The physical miniature supplies drama; the data supplies credibility. The planned token owner is `web/src/styles/tokens.css`; it does not yet exist. When implementation begins, map these semantic values there and update both in the same change rather than keeping competing token systems.

## Colors

Canvas `#101C2B` and surface `#1C2C40` establish twilight depth. Text `#F4F1E8` is warm and readable; muted text `#B4C1CE` remains intentionally light. Ambulance amber `#FFB85C` is the narrative focal point; clearance mint `#78D9CB` marks the selected corridor. Signal lenses can use traffic-specific colors, but always retain position/labels and accessible text state. Do not encode policy winners only by hue. Measure text/control contrast in the actual rendered UI before claiming WCAG compliance.

## Typography

System sans for controls and concise interpretation; system monospace with tabular numbers for time, seed and metrics. No remote font dependency for MVP. Title 28–36px, body 16px, labels 12–14px; avoid illegible cinematic microtype. English is the initial UI language; fallbacks must not corrupt names or symbols.

## Layout

Desktop: shared top control rail, one primary city canvas with a baseline ghost; optional paired inspection, a shared timeline and compact evidence strip. The city occupies roughly two-thirds of the initial viewport; results remain reachable without hiding controls. Small laptop views reduce ornament before shrinking text. Mobile uses a world toggle with the common clock and persistent mode label. Use a four-pixel spacing unit, 16–24px section gaps and no wall of interchangeable cards.

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

Validation status: design seed only; no rendered UI, contrast audit or external design linter has yet passed. An offline attempt to run the one-off design linter was blocked because its package was not cached (`ENOTCACHED`); no dependency was installed and no lint success is claimed.

## Post-review city and ghost revision

Low-poly is the art direction and performance strategy, not a temporary excuse. Use cuboid multicolored building archetypes, flat/beveled silhouettes and very few shared materials. Cars, trucks and bikes remain simple readable shapes; spend detail on the stylized ambulance hero, not every vehicle. Two hospitals are distinct landmarks. Roughly 100 pickup anchors appear only when selection is active or nearby, avoiding label clutter.

Ghost cyan `#87D7FF` is exclusive to the baseline ambulance. Use transparency/emissive material with a subtle outline or low-cost halo rather than mandatory full-screen bloom. It does not cast meaningful shadows or alter road lighting/signals. The primary scene always remains AFTERLIGHT truth; an alternate inspection view is explicitly baseline. Render-only overlaps are explained, never animated away.

The three-junction corridor is a correctness fixture inside a larger map target, not the visual limit. Zoom-level detail and landmark hierarchy keep the 25-node overview readable. Keep stable overview, deliberate follow mode and reset; no mandatory orbit. Product controls, errors, provenance and route availability are core design, not a demo-only overlay.
