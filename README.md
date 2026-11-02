# AFTERLIGHT

**Clear the ambulance’s path. Then clear the congestion left behind.**

A proposed Python-first AI traffic-signal experiment for Neural Storm 2026, FT-01 Smart Traffic Signal Optimisation. AFTERLIGHT compares emergency clearance policies across a three-intersection corridor and makes both the ambulance benefit and civilian aftermath visible.

> **Status: documentation and design only.** No simulator implementation, trained model, measured improvement, deployment, or working Blender MCP connection is claimed here. All performance numbers below are targets or experimental definitions until backed by released runs.

## Why Afterlight stands out

A basic emergency-priority demo turns a light green and celebrates the ambulance arriving sooner. **AFTERLIGHT tells the harder, more impressive story: prepare the corridor before arrival, then reveal what that decision leaves behind.** Three intersections become an architectural miniature with two synchronized futures: the same external traffic demand, different signal decisions, and an aftermath you can inspect rather than take on trust.

- **Predictive pre-clearance, not a cosmetic green wave.** A Python model is designed to learn where an analytical estimate is wrong and choose a clearance lead from observed conditions.
- **The city matters after the ambulance passes.** Civilian queues, insertion backlog and recovery remain visible. A faster emergency journey is not automatically a better overall decision.
- **Evidence built into the experience.** Paired traces, a no-learning ablation, a validation-tuned fixed lead and held-out scenarios are part of the product—not a results slide added at the end.
- **A distinctive visual instrument.** Original Blender-authored streets, a clearly readable ambulance and synchronized camera choreography make the experiment compelling without hiding its mechanics.
- **A serious zero-paid-backend delivery plan.** The real simulator runs locally; a free public viewer exposes versioned experiment replays, provenance and results without pretending recorded data is live.

Emergency preemption itself is established work. Our intended distinction is the combination of learned timing, explicit civilian aftermath and an inspectable visual experiment. **These are design advantages we are building toward, not measured superiority claims.** Learning must beat strong non-learned alternatives on held-out decisions to earn a performance claim.

## Intended deliverable

- Python/SUMO experiment with three signalized intersections and one fixed ambulance route.
- Learned timing selector compared with strong non-learned baselines on unseen whole scenarios.
- Original Blender-authored city assets and a React/Three.js experiment viewer.
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

Three documentation passes are complete; implementation and experimental validation are still pending. This README must later gain verified installation/run commands, actual screenshots, results, exact team attribution, licensing and AI-assistance disclosure before submission. Do not substitute planned commands for tested instructions.

## Boundaries

Simulation research, not a real-world traffic control system. No safety certification, real emergency deployment, or lives-saved claim. No paid services or secret-bearing files are required by the design. Public replay is explicitly recorded, not disguised as live inference.

## AI-assistance disclosure

ChatGPT assisted with research, architectural planning, documentation and critical review for this documentation stage. No implementation, trained model or generated Blender asset is claimed yet. Update this disclosure with actual implementation/asset tools and their roles as work proceeds; human review remains responsible for factual accuracy, licensing and submission compliance.
