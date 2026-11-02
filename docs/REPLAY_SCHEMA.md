# Replay v1 integration contract

`schema: afterlight.replay.v1`, `mode: recorded`. The browser is an evidence
consumer. Empty catalogs are valid; fabricated simulation results are not.

Top level:

- `scenario`: `id`, `seed`, `pickup_id`, `hospital_id`, `dispatch_s`.
- `coordinates`: source `canonical XY meters`, position reference `front_bumper`,
  render transform `[x,z,-y]`.
- `provenance`: `source_commit`, `network_sha256`, `demand_sha256`, `sumo_version`.
- `duration_s`, `step_s` and `worlds: {afterlight, baseline}`.
- Each world: `policy`, `status`, `metrics`, `events`, `frames`.
- Each frame: absolute `t`, `vehicles`, `signals`, `queue_count`.
- Vehicle: `id`, `type`, `x`, `y`, `z`, `angle_deg`, `speed_mps`, `length_m`.
  Angle is SUMO navigation degrees clockwise from north: 0 is +Y, 90 is +X.
  Pose is the front bumper: subtract half the length along heading before placing
  the center-origin Blender model. Preserve the glTF city root translation.
- Signal: canonical node `id`, actual SUMO link `state`. Do not turn a multi-link
  state into a falsely universal green. Missing approach geometry uses text.

Both worlds are independent real SUMO simulations from the same exogenous demand
file and share an absolute clock. Each may contain physical id `ambulance`; no
physical id `ghost` is created. Ghost is a renderer-only baseline ambulance clone.
Interpolate poses only, not outcomes; never retime either world or omit failed runs.

## Catalog and local adapter

Static `replays/catalog.json`: `schema: afterlight.catalog.v1`, `runs: []`, with
rows `id`, `title`, `url`, `seed`, `pickup_id`, `hospital_id`, `policy`, `duration_s`.
Only available real recordings appear. Local `GET /api/catalog` returns the same
shape with `/api/runs/{id}` URLs. Initial loopback API exposes health and recordings;
`POST` explicitly returns 501 until real generation is connected. Static mode
must not offer generation. Local mode must not call stored files live simulation.
