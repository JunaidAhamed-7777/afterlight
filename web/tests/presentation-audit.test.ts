import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import type { Replay } from "../src/types.ts";

// Explicitly synthetic contract data. These are never measured SUMO evidence.
function fixture(red = false): Replay {
  const signal = { id: "test-junction", state: red ? "r" : "G" };
  const world = (world_id: "baseline" | "afterlight") => ({
    world_id,
    policy: world_id === "baseline" ? "ordinary" : "fixed",
    status: "completed",
    metrics: { simulation_step_s: 0.5 },
    events: [
      { t: 0, junction: signal.id, kind: red ? "all_red" : "green", phase: 0 },
    ],
    frames: [0, 0.5].map((t) => ({
      t,
      queue_count: 0,
      signals: [signal],
      vehicles: [
        {
          id: "ambulance",
          type: "ambulance",
          x: t === 0 ? -1 : 1,
          y: 0,
          z: 0,
          angle_deg: 90,
          speed_mps: 4,
          length_m: 4,
          width_m: 2,
        },
      ],
    })),
  });
  return {
    schema: "afterlight.replay.v1",
    mode: "recorded",
    scenario: {
      id: "synthetic-audit-only",
      network_kind: "city",
      seed: 1,
      pickup_id: "synthetic-pickup",
      hospital_id: "synthetic-hospital",
      dispatch_s: 0,
      route_edges: ["in", "out"],
    },
    coordinates: {
      source: "canonical XY meters",
      position_reference: "front_bumper",
      render: "[x,z,-y]",
    },
    provenance: {
      source_commit: "synthetic-unit-test-only",
      source_dirty: false,
      sumo_version: "NOT A SIMULATION",
      network_sha256: "a".repeat(64),
      demand_sha256: "b".repeat(64),
    },
    network_geometry: {
      signals: [
        {
          ...signal,
          position: [0, 0, 0],
          links: [
            {
              index: 0,
              from_edge: "in",
              to_edge: "out",
              from_lane: "in_0",
              to_lane: "out_0",
              incoming_shape: [
                [-10, 0],
                [0, 0],
              ],
              outgoing_shape: [
                [0, 0],
                [10, 0],
              ],
              stop_line: [0, 0],
              turn: "s",
              via_lane: null,
            },
          ],
        },
      ],
    },
    duration_s: 0.5,
    step_s: 0.5,
    worlds: { baseline: world("baseline"), afterlight: world("afterlight") },
  };
}

function audit(
  replay: unknown,
  changeEntry?: (entry: Record<string, unknown>) => void,
) {
  const directory = fs.mkdtempSync(
    path.join(os.tmpdir(), "afterlight-audit-cli-"),
  );
  try {
    const bytes = Buffer.from(JSON.stringify(replay));
    fs.writeFileSync(path.join(directory, "recording.json"), bytes);
    const entry: Record<string, unknown> = {
      id: "synthetic-audit-only",
      title: "Synthetic test only",
      url: "recording.json",
      pickup_id: "synthetic-pickup",
      hospital_id: "synthetic-hospital",
      seed: 1,
      policy: "fixed",
      duration_s: 0.5,
      bytes: bytes.length,
      sha256: createHash("sha256").update(bytes).digest("hex"),
    };
    changeEntry?.(entry);
    fs.writeFileSync(
      path.join(directory, "catalog.json"),
      JSON.stringify({ schema: "afterlight.catalog.v1", runs: [entry] }),
    );
    return spawnSync(
      process.execPath,
      [
        "--experimental-strip-types",
        fileURLToPath(
          new URL("../scripts/audit-presentation.mjs", import.meta.url),
        ),
        "--catalog",
        path.join(directory, "catalog.json"),
      ],
      { encoding: "utf8", timeout: 10000 },
    );
  } finally {
    // Remove only this test's two known regular files, never a recursive target.
    for (const name of ["recording.json", "catalog.json"]) {
      const file = path.join(directory, name);
      if (fs.existsSync(file)) fs.unlinkSync(file);
    }
    fs.rmdirSync(directory);
  }
}

test("presentation CLI classifies a geometric green crossing and fails a red crossing", () => {
  const green = audit(fixture());
  assert.equal(green.status, 0, green.stderr);
  assert.equal(
    JSON.parse(green.stdout).results[0].worlds.afterlight.stats.crossings,
    1,
  );
  const red = audit(fixture(true));
  assert.equal(red.status, 1, red.stderr);
  assert.equal(
    JSON.parse(red.stdout).results[0].worlds.afterlight.stats.allRedJunction,
    1,
  );
});

test("presentation CLI rejects the independently found empty malformed replay", () => {
  const value = {
    schema: "afterlight.replay.v1",
    mode: "recorded",
    duration_s: 0.5,
    step_s: 0.5,
    network_geometry: { signals: [] },
    worlds: { baseline: { frames: [] }, afterlight: { frames: [] } },
  };
  const result = audit(value);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /contract/);
});

test("presentation CLI rejects empty geometry, zero coverage and mismatched catalog identity", () => {
  const empty = fixture();
  empty.network_geometry!.signals = [];
  for (const world of Object.values(empty.worlds))
    for (const frame of world.frames) frame.signals = [];
  assert.match(audit(empty).stderr, /controlled-link geometry/);
  const stationary = fixture();
  for (const world of Object.values(stationary.worlds))
    world.frames[1].vehicles[0].x = -1;
  const result = audit(stationary);
  assert.equal(result.status, 1);
  assert.equal(JSON.parse(result.stdout).status, "failed");
  assert.match(
    audit(fixture(), (entry) => {
      entry.seed = 2;
    }).stderr,
    /does not match the selected experiment/,
  );
});
