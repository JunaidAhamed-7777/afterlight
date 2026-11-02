# AFTERLIGHT

**Clear the ambulance’s path. Then clear the congestion left behind.**

A proposed Python-first AI traffic-signal experiment for Neural Storm 2026, FT-01 Smart Traffic Signal Optimisation. AFTERLIGHT compares emergency clearance policies within a planned 20–25-intersection city, beginning with a three-intersection correctness corridor and makes both the ambulance benefit and civilian aftermath visible.

> **Status: verified asset prototype; simulation and product implementation pending.** Original city and vehicle assets have been authored through a verified cloud Blender 4.3.2 MCP connection and checked. No completed simulator, trained model, measured traffic improvement or deployment is claimed. Browser WebGL rendering and frame times remain untested.

## Why Afterlight stands out

A basic emergency-priority demo turns a light green and celebrates the ambulance arriving sooner. **AFTERLIGHT tells the harder, more impressive story: prepare the corridor before arrival, then reveal what that decision leaves behind.** A compact city becomes an architectural miniature with two synchronized futures: the same external traffic demand, different signal decisions, and an aftermath you can inspect rather than take on trust.

- **Predictive pre-clearance, not a cosmetic green wave.** A Python model is designed to learn where an analytical estimate is wrong and choose a clearance lead from observed conditions.
- **The city matters after the ambulance passes.** Civilian queues, insertion backlog and recovery remain visible. A faster emergency journey is not automatically a better overall decision.
- **Evidence built into the experience.** Paired traces, a no-learning ablation, a validation-tuned fixed lead and held-out scenarios are part of the product—not a results slide added at the end.
- **A ghost that makes the counterfactual immediate.** A light-blue translucent baseline ambulance shares the same simulation clock but comes from a separate ordinary-signal world. Only the solid AFTERLIGHT ambulance affects the visible AFTERLIGHT traffic; the ghost never changes it.
- **A distinctive visual instrument.** Original Blender-authored streets, a clearly readable ambulance and synchronized camera choreography make the experiment compelling without hiding its mechanics.
- **A serious zero-paid-backend delivery plan.** The real simulator runs locally; a free public viewer exposes versioned experiment replays, provenance and results without pretending recorded data is live.

Emergency preemption itself is established work. Our intended distinction is the combination of learned timing, explicit civilian aftermath and an inspectable visual experiment. **These are design advantages we are building toward, not measured superiority claims.** Learning must beat strong non-learned alternatives on held-out decisions to earn a performance claim.

## Intended deliverable

- Python/SUMO experiment with a 20–25-intersection city target (25-node plan), two hospitals and approximately 100 pickup locations, with a three-intersection fixed-route correctness fixture.
- Learned timing selector compared with strong non-learned baselines on unseen whole scenarios.
- Original low-poly Blender-authored city assets: multicolored cuboid buildings, simple cars/trucks/bikes and a more detailed stylized ambulance; React/Three.js experiment viewer.
- Free static public replay viewer, plus local simulation and a compelling recorded demo.
- Reproducible benchmark manifests, raw outcomes, honest limitations, and setup instructions.

## Read the plan

1. [Product and contest requirements](docs/REQUIREMENTS.md)
2. [Architecture and contracts](docs/ARCHITECTURE.md)
3. [Benchmark protocol](docs/BENCHMARK_PROTOCOL.md)
4. [Visual identity](DESIGN.md) and [Blender production pipeline](docs/BLENDER_PIPELINE.md)
5. [Viewer behavior and demo](docs/VIEWER_AND_DEMO.md)
6. [Zero-cost delivery](docs/DEPLOYMENT.md)
7. [Research sources](docs/SOURCES.md) and [three-pass review record](docs/REVIEW_LOG.md)
8. [Execution roadmap, written after pass 3](docs/ROADMAP.md)

Three documentation passes and the original asset prototype are complete; simulation, viewer implementation and experimental validation are still pending. This README must later gain verified installation/run commands, actual screenshots, results, exact team attribution, licensing and AI-assistance disclosure before submission. Do not substitute planned commands for tested instructions.

## Boundaries

Simulation research, not a real-world traffic control system. No safety certification, real emergency deployment, or lives-saved claim. No paid services or secret-bearing files are required by the design. Public replay is explicitly recorded, not disguised as live inference.

## AI-assistance disclosure

ChatGPT assisted with research, architectural planning, documentation, critical review and procedural asset creation through Blender 4.3.2 and the existing Blender MCP bridge. Original geometry, source scenes, generation scripts and export checks form the asset prototype; the traffic simulation, learned model and product viewer are not implemented. Human review remains responsible for factual accuracy, licensing and submission compliance.

## Expanded city and fair comparison

The target map has 20–25 intersections (the working topology plan uses 25), two hospitals and approximately 100 pickup locations. These are a world/route-selection target, **not proof of 100 trained routes or city-wide model generalization**. The three-junction corridor remains the initial correctness fixture before city scaling. Traffic is seeded and randomized; whole demand realizations, seeds and appropriate route/regime groups are held out. Randomness alone does not establish freedom from overfitting.

The ghost is a counterfactual overlay, not a second emergency vehicle in the active world. Its independent baseline queues/signals may differ, so apparent crossings through visible AFTERLIGHT cars or red lights must be explained with a label and optional separate-world view—not cosmetically corrected. See [the updated contracts](docs/ARCHITECTURE.md).

## Verified asset milestone

The original low-poly city contains 25 primary intersections, two hospitals and 100 pickup anchors. Nine GLBs total **1,268,584 bytes**; the city is **14,552 triangles / 15 material primitives**, and the ambulance **2,378 triangles / 9 primitives**. All nine exports pass Khronos validation with zero errors or warnings. HTTP loading and GLTFLoader parsing passed for 9/9 assets, but cloud Chrome has WebGL disabled: browser drawing, frame times, ghost compositing and traffic behavior are not verified. The separate baseline-world ghost remains a runtime contract, not implemented comparison evidence.

[Explore the asset pack](assets/README.md) · [GLB validation report](assets/qa/glb_audit.json) · [Map checks](assets/map/validation_report.json)

![Original Blender city prototype — authoring preview, not a running simulation](assets/previews/city_overview.png)

This repository is the canonical source of truth for AFTERLIGHT's documentation, original assets, source scenes, generators and validation records. Asset licensing remains an explicit owner decision; see [provenance](assets/PROVENANCE.md).
