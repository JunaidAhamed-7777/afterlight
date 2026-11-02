# Three-pass review record

## Pass 1 — research and requirements

Completed documentation pass: establish the actual rubric, Python/AI requirement, local-demo allowance, deadline, narrowed FT-01 scope and the absence of verified same-organizer winner evidence. The result is a testable emergency-timing hypothesis, not a claim that emergency green corridors are new.

Changes made: explicit docs-only status; separate verified rules from proposed design; public source and AI disclosure checklist; zero-cost static replay fallback; four-hour submission contingency.

## Pass 2 — architecture and visual translation

Completed initial design pass: fix the corridor to three intersections/one route; one decision at dispatch; residual model over analytical predictor; paired full-run traces; original modular Blender assets; public recorded viewer with local Python engine.

Early adversarial corrections already integrated: bluelight disabled in primary experiment; unfinished and uninserted demand accounted; immediate priority separate from zero lead; candidate schedule collapse checked; full replay from t=0 preferred over incomplete snapshots.


## Pass 3 — independent adversarial review and revision

Completed after independent benchmark and Blender pipeline reviews. This is a documentation review, not experimental validation.

| Risk found | Revision made |
|---|---|
| “Learning” could fit analytical labels or see future demand | Scalar simulation residual formula, timestamped feature dictionary, forbidden inputs and group split specified. |
| Five candidate labels may hide identical schedules | Effective schedule deduplication and training action-diversity gate added. |
| Completed-only averages can reward stranded traffic | Full scheduled/inserted/completed/pending accounting, common drain and censoring rules added. |
| Recovery aligned to each policy’s exit can bias comparisons | Common absolute-time excess-queue area is primary; exit-aligned recovery is supplementary. |
| Best visual case could conceal a weak model | Held-out decision benefit versus analytical and fixed lead required; negative-result fallback preserved. |
| Dataset estimates could exceed remaining time | 12–20 episode end-to-end pilot gates a conditional 180-episode budget; scalar caching reduces output cost. |
| SUMO and Blender could be spatially misaligned | Network-derived manifest, one axis transform, front-bumper offset and cardinal/turning fixtures added. |
| Blender viewport appearance may not survive glTF | Thin export spike and actual GLTFLoader validation precede city production. |
| “Majestic” could consume deadline on film renders | Original miniature art direction; cut expensive offline Cycles, preserve polished browser-recorded demo. |
| Replay could be mistaken for live AI | Shared adapters, permanent provenance label and explicit disconnect behavior required. |
| MCP assumed installed or safe by name | Runtime unverified, third-party arbitrary-code boundary documented; no installation claimed. |

Remaining unknowns are implementation measurements: SUMO runtime, useful action diversity, ML improvement, actual browser performance, installed Blender/MCP capability and final host availability. They are gates, not reasons to invent results. The [roadmap](ROADMAP.md) was written after these revisions and prioritizes closing those unknowns.

## Post-three-pass user revision — expanded city and ghost (2 November, 19:43 UTC)

The user expanded the world to 20–25 intersections, two hospitals and approximately 100 pickup locations; requested low-poly multicolored cuboid scenery/traffic with a detailed ambulance; and required a light-blue baseline ghost. This is a **new scope revision**, not something the original three-pass audit already validated.

Updated the README, architecture, benchmarks, design, Blender pipeline, viewer, deployment and roadmap coherently. The ghost is render-only data from a separate ordinary baseline world, synchronized in absolute time; it has no AFTERLIGHT physics/control effects. Visible traffic/signals belong to AFTERLIGHT. Added overlap explanation, world toggle, group-held-out randomness limits, expanded-map runtime gates, graph-derived anchors, product error/accessibility states and concrete low-poly/rendering budgets. Three-junction correctness fixture retained. Documentation-first sequencing explicitly precedes renewed Blender production.

No full-city learning, finished assets, performance measurements or anti-overfitting guarantee is asserted by this update. Those require implementation and evidence.
