# Replay v1 integration contract

`schema: afterlight.replay.v1`, `mode: recorded`. The browser is an evidence
consumer. Empty catalogs are valid; fabricated simulation results are not.

Top level:

- `scenario`: `id`, `seed`, `pickup_id`, `hospital_id`, `dispatch_s`, `network_kind` (`fixture` or `city`).
  Never overlay fixture trajectories on the full-city asset.
- `coordinates`: source `canonical XY meters`, position reference `front_bumper`,
  render transform `[x,z,-y]`.
- `provenance`: `source_commit`, `network_sha256`, `demand_sha256`, `sumo_version`,
  and `canonical_map_sha256` for city overlays (null for fixtures). The browser
  compares the latter with the actual canonical-map bytes before overlaying traffic.
- `duration_s`, `step_s` and `worlds: {afterlight, baseline}`.
- Each world: matching `world_id`, physical `policy`, optional `lead_s`, `status`,
  `metrics`, `events`, `frames`. The baseline policy is `ordinary`.
- Optional `network_geometry.signals` supplies actual imported controlled-link
  shapes/indexes; this is distinct from canonical road-center route references.
- Each frame: absolute `t`, `vehicles`, `signals`, `queue_count`.
- Vehicle: `id`, `type`, `x`, `y`, `z`, `angle_deg`, `speed_mps`, `length_m`, optional positive `width_m`.
  Angle is SUMO navigation degrees clockwise from north: 0 is +Y, 90 is +X.
  Pose is the front bumper: subtract half the length along heading before placing
  the center-origin Blender model. Preserve the glTF city root translation.
- Signal: canonical node `id`, actual SUMO link `state`. Do not turn a multi-link
  state into a falsely universal green. Missing approach geometry uses text.

Both worlds are independent real SUMO simulations from the same exogenous demand
file and share an absolute clock. Each may contain physical id `ambulance`; no
physical id `ghost` is created. Ghost is a renderer-only baseline ambulance clone.
Interpolate poses only, not outcomes; never retime either world or omit failed runs.
Both frame arrays cover zero through the declared duration at identical timestamps.
Undeclared sample gaps fail validation. Insertion/removal and signals are left-held
at recorded sample boundaries; pose interpolation uses only IDs present on both
adjacent frames and does not animate detected teleport discontinuities. No pose
is extrapolated beyond trace support.

## Catalog and local adapter

Static `replays/catalog.json`: `schema: afterlight.catalog.v1`, `runs: []`, with
rows `id`, `title`, `url`, `seed`, `pickup_id`, `hospital_id`, `policy`, `duration_s`.
`policy` is the machine identity, not a display label. Optional `lead_s`,
`policy_label`, `sha256` and `bytes` retain presentation and exact-file provenance.
Selected metadata must match the fetched recording; supplied bytes/hash are
verified before displaying outcomes, with a bounded streaming response reader.
Only available real recordings appear. Local `GET /api/catalog` returns the same
shape with `/api/runs/{id}` URLs. Loopback API exposes health and recordings; generation is disabled by default.
With explicit `--enable-generation`, POST /api/runs starts one real local paired
SUMO job and GET /api/jobs/{id} reports its actual lifecycle. On completion it
provides a validated recorded replay. This is local generation followed by playback,
not live streaming. Static mode must not offer generation. See [API details](../api/README.md).

## Optional offline selector provenance extension

The optional `afterlight.selection-evidence.v1` bridge is implemented in source,
but actual selected-capture and desktop acceptance remain pending. The export
retains a predeclared real
fixed-lead candidate and ordinary comparison, with original physical policy,
raw dispatch decision and timestamps unchanged. Separate metadata identifies
the frozen selector/model, study/protocol/release/report and exact source trace
aliases/hashes. It must not relabel the physical controller as live learned
inference or infer held-out benefit from one selected run. There is currently no
released trained model, accepted selected replay or performance conclusion.

The viewer checks structural and cross-field consistency; it does not download
or independently rehash referenced scientific artifacts. The offline exporter
verifies the frozen report and original trace bindings before writing output.
See [export usage and acceptance limits](../export/README.md).
