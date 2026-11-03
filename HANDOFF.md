# AFTERLIGHT — current handoff

Work resumed on the owner’s Omen on November 3, 2026 with explicit authorization for development, tests, simulations/training and Vercel hosting. The earlier halt is preserved in [the historical handoff](docs/archive/HANDOFF-20261103-1417.md).

## Current work

The canonical city now has exactly four times its original area, 81 primary intersections, 100 pickup anchors and two hospitals in diagonal quadrants. The original Blender MCP workflow produced the new colorful 826-building city; structural and glTF validation passed. Original source scenes and vehicle GLBs are retained.

The desktop UI separates Simulation, Results and Settings, with an independently scrolling left pane and fixed right map/playback. Resource-aware loading, cancellable checksum-verified recording workers, a five-step first-visit guide, two follow controls beside Zoom, 10×/20× playback and actual-model legend previews are implemented. The ambulance roof bar alternates blue/red during playback and stays blue when paused or reduced motion is enabled. The latest follow/beacon integration is undergoing headed acceptance.

The public library contains two fully audited exploratory city pairs using the final 3 s all-red clearance profile and every 0.5 s simulation step. Cross-city response is 601 s ordinary versus 473 s fixed priority, with civilian mean excess time +2.19 s; Westhaven is 426.5 s versus 322.5 s analytical priority, with civilian mean excess time +1.14 s. All 398/426 civilians finish in each respective world, with zero collisions. These are two exploratory examples, not held-out superiority. Exact hashes and scope are in [the qualification record](docs/validation/expanded-city-qualification.json).

The final source-pinned pilot passed: twelve exploratory episodes, eighty-four audited completed worlds, 75.3 minutes measured wall time and useful action diversity. Earlier failed and superseded attempts remain retained. The [study is frozen](docs/validation/study-v4/frozen-protocol.json) at `fa39f8a` with 24 training, 12 validation and 20 test cases, a common 3000 s endpoint, three-second city clearance, heavy-demand and route-family holdouts, and disjoint seeds 22001–22056. Root independently checked the copied protocol/study digests and split/exclusion metadata without opening any outcomes. Training/validation collection precedes model/selector freezing; test remains separately released once. No fitted model or held-out benefit is claimed while those stages remain pending.

Results now separates **This run** from **Study**. The Study view accepts only a bounded checksum-bound summary of an actually audited released report, with failures, paired deltas, uncertainty and downloadable proof. Its real positive-data acceptance awaits the completed study; missing or invalid publication never creates placeholder metrics. The public viewer remains a static replay/evidence product, without a hosted simulator or live learned controller.

## Services and preserved evidence

Task-owned development: port 5182. Immutable production QA snapshots remain under `local-runtime/`; their manifests identify exact source and output bytes. Current local API jobs on 8784 and 8786 have passed GET-only browser recovery without duplicate submission. The heavy job's original 157,189,187-byte replay passed streamed SHA verification before/after reload and four public/local switches, with its journal/raw inventory unchanged. Original user-demo ports, historical checkouts and scientific artifacts remain preserved.

Depth fighting is corrected with logarithmic depth and separated hospital plaza/road surfaces. Seven-angle camera sweeps at 1920×1080 and 2560×1440 produced fourteen identical paused-repeat screenshot pairs, with independent pixel review. The final dense presentation audit covers 9,839 eligible stop-line crossings with zero red/all-red crossings or unresolved movements. The [desktop acceptance record](docs/validation/desktop-v4-acceptance.json) binds each scoped check to its actual build; older performance measurements do not automatically apply to later revisions.

Do not edit the isolated engine checkout while a run is active. Do not regenerate old evidence to obtain screenshots. Current source, compiled previews and scientific provenance are distinct checkpoints. The portable preview helper supports Windows without weakening exact-HEAD byte checks. The committed preview was rebuilt and verified before the Study UI addition; rebuild it again after the remaining Study review fixes. Exact scientific companions use narrow `-text` attributes so their original byte hashes survive checkout. Commit small logical diffs frequently and push to `main` regularly, as explicitly requested.

## Required before completion

- Complete collection of the frozen group-disjoint study, fit/select on training/validation, release untouched test once, and verify the actual published Study view.
- Preserve completed expanded local API idempotency/restart/recovery evidence; finish latest follow/beacon headed acceptance.
- Finish independent review, two final polish passes and production desktop/performance acceptance.
- Deploy on Vercel, create identity through Canva, integrate and redeploy; then finish README with real screenshots and exact measured results.

Desktop only. No mobile optimization or acceptance runs are required.
