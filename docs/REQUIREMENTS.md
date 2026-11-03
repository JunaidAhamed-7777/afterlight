# Product requirements and evidence boundaries

## Historical contest-rules snapshot

The original review used the organizer pages linked in [Sources](SOURCES.md). This table preserves that review; the product update has not reverified organizer rules. Recheck the current rules before submission.

| Requirement | Consequence for AFTERLIGHT |
|---|---|
| Neural Storm 2026 build window: November 2, 20:00 IST to November 4, 20:00 IST | Build within the window; target a complete submission by November 4, 16:00 IST, preserving four hours of contingency. |
| Python-primary AI/ML project | Simulation, datasets, learned model, evaluation and trace export are Python-led. A JavaScript presentation layer does not replace the AI contribution. |
| FT-01 Smart Traffic Signal Optimisation | Narrow to emergency-corridor timing and the civilian recovery problem. Explain this interpretation explicitly. |
| Public complete GitHub source | Publish reproducible source, configuration, documented dependencies and artifact provenance; exclude credentials and unrelated private files. |
| Deployment strongly recommended, not mandatory | Static replay plus local runnable engine is viable; demo polish does not justify pretending a replay is live. |
| Technical 35%, impact 25%, documentation 20%, demo 20% | Secure technical correctness and reproducibility before visual extras. |
| Tie-break: technical merit, then earlier submission | Deliver a valid entry early, update before close if allowed; do not gamble on the final minute. |
| Libraries/pretrained models/APIs/AI coding assistance allowed with disclosure | Record material tools, sources and AI assistance in the final README. |
| One entry per team; student/age eligibility requirements apply | Verify registration/team details privately; do not infer compliance from this public document. |

Submission README checklist: title; problem number; team names; problem and solution; stack; setup/local execution; screenshots/GIF; metrics; AI assistance disclosure. Exact team member consent and final submission fields remain operational checks, not facts to fabricate.

## Research conclusion

No verified prior winning project from this exact organizing team was established. Related regional hackathon results are weak contextual evidence, not a reliable predictor of this jury. ACE Hack Fest 2020 lists Jal-Bhat, Mountain Areas Accident Prevention, Swachaalan and a Women Safety consolation award; those results do not establish architectures, evaluation rigor, or a winning formula for Neural Storm. Optimise against this contest’s explicit rubric, not invented judge preferences.

## User and problem

The demo audience is a technical judge asking whether intelligent emergency priority improves transport outcomes without merely shifting harm to cross traffic. The prototype user is a traffic analyst exploring a small corridor, not a dispatcher operating real infrastructure.

**Research question:** on held-out simulated demand, does learned residual prediction improve a constrained timing decision over a tuned fixed lead and the same analytical planner without learning?

**Secondary question:** what happens after the ambulance exits? Report civilian delay, backlog and recovery alongside the ambulance journey.

## Scope lock

Current canonical map: 81 primary intersections in a 9×9 grid, 120 additional service/access nodes, two hospitals in diagonal quadrants and 100 pickup locations; original low-poly city with simple multicolored buildings and traffic archetypes; one detailed stylized ambulance. Keep a three-intersection fixed-route fixture for controller correctness before city scaling. First validated learning experiment may remain corridor-scoped; exposing map pickup selection does not prove learned arbitrary-route performance. One ambulance per independently simulated world, one dispatch decision, shared legal scheduler across priority variants and seeded paired demand remain constraints. A render-only baseline ghost overlays the active AFTERLIGHT world.

Out of scope: real road control, multiple simultaneous emergency dispatches, arbitrary city import, reinforcement learning training, live sensor integration, cloud GPU inference, accounts, collaborative editing, external geographic address search, medical claims, paid APIs.

## Definition of impressive

The visual signature is one synchronized city shown in two counterfactual outcomes, then an aftermath reveal. The scientific signature is an honest ablation explaining whether learning helps. A small, convincing experiment beats a large untestable command center. If the learned model loses, show that clearly and investigate; never cherry-pick a cinematic win and label it the overall result.

## Map coverage and scope changes

The city and ghost overlay were added after the original three-pass review; the owner subsequently requested the current fourfold expansion. They require new topology, route-connectivity, runtime and world-isolation checks; the earlier review is not evidence those expanded checks already passed. The published 100 pickups are canonical route anchors, not 100 extra intersections. Exact IDs, hospital connections and pickup placement belong to the authoritative graph manifest, not independently invented frontend coordinates.

Graph reachability acceptance targets all 200 possible pickup/hospital pairs, with deterministic curb-anchor IDs and valid vehicle permissions. Benchmark coverage is reported separately; a connected pair is not an evaluated scenario. The current district spans 2,040 × 2,010 m, about 4.10 km²: exactly four times the original footprint area. It has 77 signalized primary junctions. Primary nodes and signal controllers are different counts; the authoritative manifest and network qualification own those counts.

## Current desktop product requirements

The owner prioritizes desktop-only usability and performance. Preserve keyboard
access, reduced-motion support and normal window resizing; do not expand mobile
optimization or testing. Use actual modeled 3D buildings and roads, not parallax
or billboard substitutes. Provide true-perspective exploration at 2.5× visual
magnification, X/Y/Z camera controls, a fitted overview and selective foreground
building cutaway as an explicit option, off by default. Magnification must not alter canonical meters or routes. The left Simulation/Results/Settings pane scrolls independently; the right city, camera and playback stay visible in a 16:9 desktop window.

The owner permits up to 50,000,000 bytes for the shipped static product assets, including compressed recordings. This build/transfer budget is separate from the 128 MiB decoded-JSON guard for an individual dense recording. Simple low-poly cars/trucks/bikes and an identifiable
hero ambulance remain intentional. Optional map picking must use real canonical
anchors, distinguish a click from camera dragging and preserve complete HTML
search/dropdown alternatives. Recorded-world comparison controls appear only
when real paired evidence is loaded. Provide a skippable, repeatable first-visit
walkthrough, separate solid-ambulance/ordinary-ghost follow controls, actual-model
legend thumbnails and playback speeds through 20×. Generation settings may be simplified, but
saved request identity, failure reasons and uncertain-request recovery remain explicit.

## Current delivery contract

The public product is a static replay viewer targeting Vercel. It includes two
audited exploratory city pairs with real cars, bikes and trucks. Current
captures use 3 s all-red clearance and retain every 0.5 s simulation step through
their common 900 s endpoint.
Gzip changes transport size, not recorded poses or outcomes. The local
Python/SUMO runner is a separate, explicitly enabled capability.

Loading must remain usable while recordings are fetched, decompressed, checked
and parsed in a worker. Cancellation, useful errors, graphics retry and HTML
outcomes remain available. Signal arrows represent individual controlled
movements using exact recorded boundaries; a junction is never universally green.
Public recording availability, graph reachability, local generation and a held-out
scientific result are distinct claims.

The original 25-primary-junction/25 MB plan is historical. Its acceptance records
retain their source IDs and do not validate later revisions. Current artifacts
and exploratory evidence are linked from the [documentation index](README.md).
Learned-policy claims require a separate frozen study release.
