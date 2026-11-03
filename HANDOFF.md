# AFTERLIGHT — current handoff

Work resumed on the owner’s Omen on November 3, 2026 with explicit authorization for development, tests, simulations/training and Vercel hosting. The earlier halt is preserved in [the historical handoff](docs/archive/HANDOFF-20261103-1417.md).

## Current work

The canonical city now has exactly four times its original area, 81 primary intersections, 100 pickup anchors and two hospitals in diagonal quadrants. The original Blender MCP workflow produced the new colorful 826-building city; structural and glTF validation passed. Original source scenes and vehicle GLBs are retained.

The desktop UI now separates Simulation, Results and Settings, with an independently scrolling left pane and a fixed right map/playback. A resource-aware loading screen, actual recording default, world isolation, exact signal boundary presentation and a Locate ambulance action are implemented. Current production browser and performance qualification is running; final results will replace this in-progress note.

One expanded-city seed-7 fixed-priority recording passed full raw simulation audits. Each world completed all 398 civilians with no collisions, teleports, running or uninserted vehicles. Ambulance journeys were 561 s ordinary and 455 s fixed priority; civilian mean excess time increased from 99.588 s to 101.717 s. This is a single exploratory qualification case, not held-out superiority. Exact hashes and scope are in [the qualification record](docs/validation/expanded-city-qualification.json).

A source-pinned twelve-episode pilot is running in `C:/Github/afterlight-engine-v4`. Study collection and fitting will follow only if pilot validity and action diversity pass. Public static hosting does not run SUMO or inference. No learned benefit is claimed before real evaluation completes.

## Services and preserved evidence

Task-owned development: port 5182. An immutable production QA snapshot is served on 5185. The retained old completed API job has been recovered through GET-only requests on 8780 and a separately configured current viewer on 5184; its original journal and raw inventory are unchanged. That older recording correctly shows an old-map geometry mismatch in the expanded viewer. Original user-demo ports and files remain preserved.

Do not edit the isolated engine checkout while a run is active. Do not regenerate old evidence to obtain screenshots. Current source, compiled previews and scientific provenance are distinct checkpoints. The old committed `preview/` remains source-bound to its historical revision until it is deliberately rebuilt and verified.

## Required before completion

- Complete pilot, freeze and run a group-disjoint study, fit/select on training/validation, release untouched test once.
- Verify the expanded local API protocol through actual idempotency/restart/recovery.
- Finish independent review, two final polish passes and production desktop/performance acceptance.
- Deploy on Vercel, create identity through Canva, integrate and redeploy; then finish README with real screenshots and exact measured results.

Desktop only. No mobile optimization or acceptance runs are required.
