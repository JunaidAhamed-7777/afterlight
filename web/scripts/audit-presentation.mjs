// Read-only presentation audit. Scientific tripinfo/lifecycle audits remain separate.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { gunzipSync } from "node:zlib";
import { buildSignalTimeline } from "../src/signalTimeline.ts";
import { validateCatalog } from "../src/catalog.ts";
import { validateReplay } from "../src/replay.ts";
import { bindRecording } from "../src/recordingCore.ts";
const args = process.argv.slice(2);
function argument(name, fallback) {
  const index = args.indexOf(name);
  if (index < 0) return fallback;
  if (!args[index + 1] || args[index + 1].startsWith("--"))
    throw Error("Missing value: " + name);
  return args[index + 1];
}
if (
  args.some(
    (arg, index) => index % 2 === 0 && !["--catalog", "--output"].includes(arg),
  ) ||
  args.length % 2
)
  throw Error(
    "Usage: node --experimental-strip-types web/scripts/audit-presentation.mjs [--catalog catalog.json] [--output new-report.json]",
  );
const catalogPath = path.resolve(
  argument("--catalog", "web/public/replays/catalog.json"),
);
const outputPath = argument("--output", null);
const dir = path.dirname(catalogPath);
const catalog = JSON.parse(fs.readFileSync(catalogPath, "utf8"));
validateCatalog(catalog, "http://127.0.0.1/catalog.json");
if (
  catalog.schema !== "afterlight.catalog.v1" ||
  !Array.isArray(catalog.runs) ||
  !catalog.runs.length
)
  throw Error("Expected a nonempty AFTERLIGHT public catalog");
const sha256 = (bytes) =>
  crypto.createHash("sha256").update(bytes).digest("hex");
const helperPath = new URL("../src/signalTimeline.ts", import.meta.url);
const moduleDirectory = new URL("../src/", import.meta.url);
const moduleSourceSha256 = Object.fromEntries(
  fs
    .readdirSync(moduleDirectory)
    .filter((name) => name.endsWith(".ts"))
    .sort()
    .map((name) => [
      name,
      sha256(fs.readFileSync(new URL(name, moduleDirectory))),
    ]),
);
const clean = (v) => Math.round(v * 1e5) / 1e5;
function dot(p, a, d) {
  return (p.x - a[0]) * d[0] + (p.y - a[1]) * d[1];
}
function lateral(p, a, d) {
  return Math.abs((p.x - a[0]) * d[1] - (p.y - a[1]) * d[0]);
}
function direction(a, b) {
  const x = b[0] - a[0],
    y = b[1] - a[1],
    l = Math.hypot(x, y);
  return [x / l, y / l, l];
}
function align(angle, d) {
  const a = (angle * Math.PI) / 180;
  return Math.sin(a) * d[0] + Math.cos(a) * d[1];
}
function at(changes, t) {
  let l = 0,
    h = changes.length - 1;
  if (h < 0 || changes[0].t > t) return undefined;
  while (l < h) {
    let m = Math.ceil((l + h) / 2);
    if (changes[m].t <= t) l = m;
    else h = m - 1;
  }
  return changes[l].state;
}
function futureMovement(rows, frameIndex, id, links) {
  for (
    let k = frameIndex + 1;
    k < rows.length && rows[k].t <= rows[frameIndex].t + 10;
    k++
  ) {
    const v = rows[k].vehicles.find((v) => v.id === id);
    if (!v) continue;
    const candidates = [];
    for (const link of links) {
      const a = link.outgoing_shape[0],
        b = link.outgoing_shape[1],
        d = direction(a, b),
        p = dot(v, a, d),
        dist = lateral(v, a, d);
      if (p > 0.3 && p < d[2] && dist < 0.8 && align(v.angle_deg, d) > 0.98)
        candidates.push(link);
    }
    const indices = [...new Set(candidates.map((c) => c.index))];
    if (indices.length === 1)
      return {
        index: indices[0],
        matchedAt: rows[k].t,
        method: "unique_future_outgoing_lane_pose_and_heading",
        toLanes: [...new Set(candidates.map((c) => c.to_lane))],
      };
  }
  return null;
}
const results = [];
for (const item of catalog.runs) {
  if (
    typeof item.url !== "string" ||
    path.isAbsolute(item.url) ||
    item.url.includes("..") ||
    item.url.includes("\\")
  )
    throw Error("Expected a safe local catalog recording name");
  const file = path.join(dir, item.url);
  const physicalSize = fs.statSync(file).size;
  if (physicalSize > 20 * 1024 * 1024)
    throw Error("Physical public recording exceeds 20 MiB");
  const raw = fs.readFileSync(file);
  if (
    item.encoding === "gzip" &&
    (raw.length !== item.transfer_bytes || sha256(raw) !== item.transfer_sha256)
  )
    throw Error("Gzip transfer length/checksum differs: " + file);
  const bytes =
    raw[0] === 0x1f && raw[1] === 0x8b
      ? gunzipSync(raw, { maxOutputLength: 128 * 1024 * 1024 })
      : raw;
  const hash = sha256(bytes);
  if (
    bytes.length > 128 * 1024 * 1024 ||
    bytes.length !== item.bytes ||
    hash !== item.sha256
  )
    throw Error("Decoded public recording length/checksum differs: " + file);
  const replay = bindRecording(validateReplay(JSON.parse(bytes)), item);
  if (
    replay.scenario.network_kind !== "city" ||
    replay.provenance.source_dirty !== false ||
    !replay.network_geometry?.signals.length ||
    replay.network_geometry.signals.some((signal) => !signal.links.length)
  )
    throw Error(
      "Expected a clean-source city recording with controlled-link geometry",
    );
  if (
    item.source_commit !== undefined &&
    item.source_commit !== replay.provenance.source_commit
  )
    throw Error("Catalog source commit differs from recorded provenance");
  if (replay.step_s !== 0.5)
    throw Error(
      "Presentation review requires the declared 0.5-second capture cadence",
    );
  const grid = new Map();
  const cell = 16;
  for (const signal of replay.network_geometry.signals) {
    const groups = new Map();
    for (const link of signal.links) {
      const list = groups.get(link.from_lane) || [];
      list.push(link);
      groups.set(link.from_lane, list);
    }
    for (const [lane, links] of groups) {
      const a = links[0].incoming_shape.at(-2),
        b = links[0].incoming_shape.at(-1),
        d = direction(a, b);
      const record = {
        signal: signal.id,
        lane,
        links,
        point: b,
        d,
        indices: [...new Set(links.map((l) => l.index))],
      };
      const key = Math.floor(b[0] / cell) + "," + Math.floor(b[1] / cell);
      const list = grid.get(key) || [];
      list.push(record);
      grid.set(key, list);
    }
  }
  const worlds = {};
  for (const name of ["afterlight", "baseline"]) {
    const world = replay.worlds[name],
      frames = world.frames,
      timeline = buildSignalTimeline(world);
    if (
      world.metrics.simulation_step_s !== 0.5 ||
      frames.length !== replay.duration_s / 0.5 + 1 ||
      frames.some((frame, index) => Math.abs(frame.t - index * 0.5) > 1e-9)
    )
      throw Error("Actual pose samples do not match every simulation step");
    const stats = {
      crossings: 0,
      exactTimelineSignals: timeline.size,
      totalSignals: replay.network_geometry.signals.length,
      allRedJunction: 0,
      allLaneMovementsRed: 0,
      inferredMovementRed: 0,
      ambiguousMixedRed: 0,
      unclassifiedWithoutTimeline: 0,
      greenOrYellowOrOff: 0,
      yellowMovements: 0,
    };
    const red = [],
      ambiguous = [];
    for (let k = 0; k < frames.length - 1; k++) {
      const left = frames[k],
        right = frames[k + 1],
        next = new Map(right.vehicles.map((v) => [v.id, v]));
      for (const v of left.vehicles) {
        const n = next.get(v.id);
        if (!n || n.type !== v.type) continue;
        const travelled = Math.hypot(n.x - v.x, n.y - v.y, n.z - v.z);
        if (
          travelled < 0.001 ||
          travelled >
            Math.max(v.speed_mps, n.speed_mps, 1) * (right.t - left.t) * 2 +
              v.length_m * 2 +
              5
        )
          continue;
        const candidates = new Set();
        for (
          let xx = Math.floor((Math.min(v.x, n.x) - 2) / cell);
          xx <= Math.floor((Math.max(v.x, n.x) + 2) / cell);
          xx++
        )
          for (
            let yy = Math.floor((Math.min(v.y, n.y) - 2) / cell);
            yy <= Math.floor((Math.max(v.y, n.y) + 2) / cell);
            yy++
          )
            for (const lane of grid.get(xx + "," + yy) || [])
              candidates.add(lane);
        for (const lane of candidates) {
          if (align(v.angle_deg, lane.d) < 0.9) continue;
          const before = dot(v, lane.point, lane.d),
            after = dot(n, lane.point, lane.d);
          if (before >= -0.001 || after < 0.001) continue;
          const alpha = -before / (after - before),
            t = left.t + (right.t - left.t) * alpha;
          const p = {
            x: v.x + (n.x - v.x) * alpha,
            y: v.y + (n.y - v.y) * alpha,
          };
          if (
            lateral(p, lane.point, lane.d) > 1.5 ||
            lateral(v, lane.point, lane.d) > 1.6
          )
            continue;
          stats.crossings++;
          const changes = timeline.get(lane.signal),
            state = changes ? at(changes, t) : undefined;
          if (!state) {
            stats.unclassifiedWithoutTimeline++;
            continue;
          }
          const values = lane.indices.map((i) => state[i]);
          if (
            values.some((value) => !value || !/^[rRyYgGoOuUs]$/.test(value))
          ) {
            stats.unclassifiedWithoutTimeline++;
            continue;
          }
          const allRed = values.every((s) => s === "r" || s === "R");
          const details = {
            stopLine: lane.point,
            incomingVector: lane.d.slice(0, 2),
            vehicle: v.id,
            type: v.type,
            junction: lane.signal,
            fromLane: lane.lane,
            linkIndices: lane.indices,
            t: clean(t),
            interval: [left.t, right.t],
            alpha: clean(alpha),
            leftSpeed: v.speed_mps,
            rightSpeed: n.speed_mps,
            beforeDistance: clean(-before),
            afterDistance: clean(after),
            crossingPoint: [clean(p.x), clean(p.y)],
            exactState: state,
            laneStates: values.join(""),
            leftPose: [v.x, v.y, v.angle_deg],
            rightPose: [n.x, n.y, n.angle_deg],
          };
          if (allRed) {
            if (/^[rR]+$/.test(state)) {
              stats.allRedJunction++;
              details.classification = "whole_junction_all_red";
            } else {
              stats.allLaneMovementsRed++;
              details.classification = "all_legal_movements_from_this_lane_red";
            }
            const prev = changes.filter((c) => c.t <= t).at(-1),
              future = changes.filter((c) => c.t > t);
            details.previousBoundary = prev;
            details.nextBoundary = future[0];
            red.push(details);
            continue;
          }
          if (!values.some((s) => s === "r" || s === "R")) {
            stats.greenOrYellowOrOff++;
            if (values.some((s) => s === "y" || s === "Y"))
              stats.yellowMovements++;
            continue;
          }
          let movement = null;
          if (
            v.id === "ambulance" &&
            Array.isArray(replay.scenario.route_edges)
          ) {
            const route = replay.scenario.route_edges;
            const candidates = lane.links.filter((link) =>
              route.some(
                (edge, index) =>
                  edge === link.from_edge && route[index + 1] === link.to_edge,
              ),
            );
            const indices = [...new Set(candidates.map((link) => link.index))];
            if (indices.length === 1)
              movement = {
                index: indices[0],
                method: "declared_ambulance_route_and_geometric_incoming_lane",
                toLanes: [...new Set(candidates.map((link) => link.to_lane))],
              };
          }
          movement ??= futureMovement(frames, k, v.id, lane.links);
          if (movement) {
            if (
              state[movement.index] === "r" ||
              state[movement.index] === "R"
            ) {
              stats.inferredMovementRed++;
              red.push({
                ...details,
                classification:
                  "unique_future_outgoing_lane_matches_red_controlled_movement",
                movement,
              });
            } else {
              stats.greenOrYellowOrOff++;
              if (
                state[movement.index] === "y" ||
                state[movement.index] === "Y"
              )
                stats.yellowMovements++;
            }
          } else {
            stats.ambiguousMixedRed++;
            ambiguous.push({
              ...details,
              classification:
                "mixed_movement_states_without_authoritative_vehicle_lane_or_route_metadata",
            });
          }
        }
      }
    }
    worlds[name] = { stats, red, ambiguous };
  }
  results.push({
    id: item.id,
    title: item.title,
    decodedSha256: hash,
    step_s: replay.step_s,
    sourceCommit: replay.provenance.source_commit,
    worlds,
  });
}
const failed = results.some((result) =>
  Object.values(result.worlds).some(
    (world) =>
      !world.stats.crossings ||
      world.stats.exactTimelineSignals !== world.stats.totalSignals ||
      world.stats.allRedJunction ||
      world.stats.allLaneMovementsRed ||
      world.stats.inferredMovementRed ||
      world.stats.ambiguousMixedRed ||
      world.stats.unclassifiedWithoutTimeline,
  ),
);
const report = {
  schema: "afterlight.presentation-crossing-review.v1",
  method:
    "Incoming lane stop-line crossing of the production linear interpolated SUMO front-bumper pose, within1.5m lateral lane center and incoming heading alignment>.90. Exact lamp timelines use production buildSignalTimeline and reproduce all saved frames. Mixed movement classification is separately labeled inferred when a unique future outgoing-lane pose+heading matches; unresolved movement is never guessed. These are presentation checks, not raw physics/safety certification. Teleport-like, same-position, missing-neighbor and differently typed pose pairs are ineligible. Yellow crossings are counted separately from red and are not a braking-acceptance certificate.",
  auditSourceSha256: sha256(fs.readFileSync(new URL(import.meta.url))),
  signalTimelineSourceSha256: sha256(fs.readFileSync(helperPath)),
  moduleSourceSha256,
  catalogSha256: sha256(fs.readFileSync(catalogPath)),
  nodeVersion: process.version,
  status: failed ? "failed" : "passed",
  results,
};
const serialized = JSON.stringify(report, null, 2) + "\n";
if (outputPath) fs.writeFileSync(outputPath, serialized, { flag: "wx" });
console.log(serialized);
if (failed) process.exitCode = 1;
