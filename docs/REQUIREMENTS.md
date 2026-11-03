# Pass 1 — requirements, evidence, and product

## Contest fit

Verified against organizer pages linked in [Sources](SOURCES.md); recheck immediately before submission because organizer updates can supersede this snapshot.

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

Current canonical map: 25 primary intersections plus separately identified service/driveway nodes, two hospitals and 100 pickup locations; original low-poly city with simple multicolored buildings and traffic archetypes; one detailed stylized ambulance. Keep a three-intersection fixed-route fixture for controller correctness before city scaling. First validated learning experiment may remain corridor-scoped; exposing map pickup selection does not prove learned arbitrary-route performance. One ambulance per independently simulated world, one dispatch decision, shared legal scheduler across priority variants and seeded paired demand remain constraints. A render-only baseline ghost overlays the active AFTERLIGHT world.

Out of scope: real road control, multiple simultaneous emergency dispatches, arbitrary city import, reinforcement learning training, live sensor integration, cloud GPU inference, accounts, collaborative editing, external geographic address search, medical claims, paid APIs.

## Definition of impressive

The visual signature is one synchronized city shown in two counterfactual outcomes, then an aftermath reveal. The scientific signature is an honest ablation explaining whether learning helps. A small, convincing experiment beats a large untestable command center. If the learned model loses, show that clearly and investigate; never cherry-pick a cinematic win and label it the overall result.

## Post-review scope change

The expanded map and ghost overlay were requested after the original three-pass review. They require new topology, route-connectivity, runtime and world-isolation checks; the earlier review is not evidence those expanded checks already passed. The published 100 pickups are canonical route anchors, not 100 extra intersections. Exact IDs, hospital connections and pickup placement belong to the authoritative graph manifest, not independently invented frontend coordinates.

Graph reachability acceptance targets all 200 possible pickup/hospital pairs, with deterministic curb-anchor IDs and valid vehicle permissions. Benchmark coverage is reported separately; a connected pair is not an evaluated scenario. The expanded district should feel roughly kilometer-scale while keeping primary intersections near 25; service-road geometry does not require hundreds of extra signal controllers.

## Current desktop product requirements

The owner prioritizes desktop-only usability and performance. Preserve keyboard
access, reduced-motion support and normal window resizing; do not expand mobile
optimization or testing. Use actual modeled 3D buildings and roads, not parallax
or billboard substitutes. Provide true-perspective exploration at 2.5× visual
magnification, X/Y/Z camera controls, a fitted overview and selective foreground
building transparency. Magnification must not alter canonical meters or routes.

The map asset ceiling is 25 MB. Simple low-poly cars/trucks/bikes and an identifiable
hero ambulance remain intentional. Optional map picking must use real canonical
anchors, distinguish a click from camera dragging and preserve complete HTML
search/dropdown alternatives. Recorded-world comparison controls appear only
when real paired evidence is loaded. Generation settings may be simplified, but
saved request identity, failure reasons and uncertain-request recovery remain explicit.
