# Documentation

Start with [the viewer setup](../web/README.md), then choose the contract you need:

- [Product requirements](REQUIREMENTS.md): desktop scope, city and evidence boundaries.
- [Architecture](ARCHITECTURE.md): simulation, replay, coordinates and world isolation.
- [Viewer behavior](VIEWER_AND_DEMO.md) and [3D camera](CAMERA_AND_3D_MAP.md): controls and recovery.
- [Replay schema](REPLAY_SCHEMA.md): frame/catalog integration contract.
- [Local runner](../api/README.md): explicit loopback generation and saved-job recovery.
- [Benchmark protocol](BENCHMARK_PROTOCOL.md) and [study workflow](../evaluation/STUDY.md): scientific evaluation.
- [Blender pipeline](BLENDER_PIPELINE.md) and [asset inventory](../assets/README.md): original geometry and provenance.
- [Vercel deployment](DEPLOYMENT.md): static build, transfer budget and release checks.
- [Visual identity](../DESIGN.md), [roadmap](ROADMAP.md) and [handoff](../HANDOFF.md).

The current canonical city has 81 primary junctions, 77 signal controllers, two
hospitals in diagonal quadrants and 100 pickups across a fourfold footprint.
The static public library includes two audited exploratory pairs at 0.5 s cadence
with 3 s all-red clearance.
The product budget is 50 MB of shipped assets, including gzip recordings; each
decoded recording has a separate 128 MiB reader guard. Desktop is the sole
optimization and default browser-acceptance target.

Current artifact evidence:

- [Expanded network qualification](validation/expanded-network-qualification.json): all 200 routes, distinct from benchmark coverage.
- [Published recording evidence](validation/expanded-city-recordings.json): exact source, cadence, transport and outcome identities.
- [Presentation crossing review](validation/expanded-city-presentation.json): source-bound, geometry-eligible stop-line classifications; separate from raw simulator audits.
- [Expanded city qualification](validation/expanded-city-qualification.json): one exploratory pair and its audit scope.
- [City geometry acceptance](../assets/qa/city_expanded_acceptance.json) and [Khronos report](../assets/qa/city_expanded_gltf_audit.json).

Exploratory playback, passed software checks and a fitted model are separate
from a held-out performance conclusion. Use the final frozen study/report for
any learned-policy claim; these product documents do not assert such a benefit.

[The chronological Omen log](validation/OMEN_LOG.md), [implementation checkpoints](IMPLEMENTATION_STATUS.md),
[sources](SOURCES.md) and [review log](REVIEW_LOG.md) preserve earlier decisions
and evidence. Their old map counts, empty catalogs, pending gates and measurements
belong to their recorded commits. They are not the current product status and
must not be silently upgraded into acceptance for later source.
