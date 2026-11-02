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

MVP: three intersections; one network; one fixed route; one ambulance; explicit dispatch instant; discrete clearance leads; shared legal signal scheduler; one policy decision at dispatch; paired full-run replays; deterministic recorded visualizations.

Out of scope: real road control, multiple ambulance routing, arbitrary city import, reinforcement learning training, live sensor integration, cloud GPU inference, accounts, collaborative editing, map search, medical claims, paid APIs.

## Definition of impressive

The visual signature is one synchronized city shown in two counterfactual outcomes, then an aftermath reveal. The scientific signature is an honest ablation explaining whether learning helps. A small, convincing experiment beats a large untestable command center. If the learned model loses, show that clearly and investigate; never cherry-pick a cinematic win and label it the overall result.
