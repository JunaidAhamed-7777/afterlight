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

function outsideRuntimeDirectory(prefix: string): string {
  const checkout = fs.realpathSync(fileURLToPath(new URL("../../", import.meta.url)));
  const runtime = path.join(checkout, "local-runtime");
  const canonicalRuntime = fs.existsSync(runtime) ? fs.realpathSync(runtime) : runtime;
  const isInsideRuntime = (directory: string) => {
    const relative = path.relative(canonicalRuntime, directory);
    return relative === "" || (!path.isAbsolute(relative) && relative !== ".." && !relative.startsWith(".." + path.sep));
  };
  // Acceptance deliberately redirects every temp variable into local-runtime.
  // Boundary-rejection fixtures must still physically live outside that tree.
  const temporary = fs.realpathSync(os.tmpdir());
  const base = isInsideRuntime(temporary) ? checkout : temporary;
  const directory = fs.mkdtempSync(path.join(base, prefix));
  if (isInsideRuntime(fs.realpathSync(directory))) {
    fs.rmdirSync(directory); // Only this newly created, still-empty fixture.
    assert.fail("Outside-runtime fixture resolved inside local-runtime");
  }
  return directory;
}

function audit(
  replay: unknown,
  changeEntry?: (entry: Record<string, unknown>) => void,
  options: {
    local?: boolean;
    args?: string[];
    physicalBytes?: number;
    redirectedRecording?: boolean;
  } = {},
) {
  const localRoot = fileURLToPath(new URL("../../local-runtime/", import.meta.url));
  if (options.local) fs.mkdirSync(localRoot, { recursive: true });
  const directory = options.local
    ? fs.mkdtempSync(path.join(localRoot, "afterlight-audit-cli-"))
    : outsideRuntimeDirectory("afterlight-audit-cli-");
  let externalDirectory: string | undefined;
  try {
    const bytes = Buffer.from(JSON.stringify(replay));
    fs.writeFileSync(path.join(directory, "recording.json"), bytes);
    if (options.physicalBytes !== undefined)
      fs.truncateSync(path.join(directory, "recording.json"), options.physicalBytes);
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
    if (options.redirectedRecording) {
      externalDirectory = outsideRuntimeDirectory("afterlight-audit-outside-");
      fs.renameSync(path.join(directory, "recording.json"), path.join(externalDirectory, "recording.json"));
      fs.symlinkSync(externalDirectory, path.join(directory, "redirected"), process.platform === "win32" ? "junction" : "dir");
      entry.url = "redirected/recording.json";
    }
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
        ...(options.args ?? []),
      ],
      { encoding: "utf8", timeout: 10000 },
    );
  } finally {
    if (externalDirectory !== undefined) {
      const link = path.join(directory, "redirected");
      if (fs.existsSync(link)) fs.unlinkSync(link);
      fs.unlinkSync(path.join(externalDirectory, "recording.json"));
      fs.rmdirSync(externalDirectory);
    }
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
  assert.deepEqual(
    JSON.parse(green.stdout).results[0].worlds.afterlight.stats.crossingsByVehicleType,
    { ambulance: 1 },
  );
  assert.equal(JSON.parse(green.stdout).results[0].worlds.afterlight.status, "completed");
  const red = audit(fixture(true));
  assert.equal(red.status, 1, red.stderr);
  assert.equal(
    JSON.parse(red.stdout).results[0].worlds.afterlight.stats.allRedJunction,
    1,
  );
});

test("local presentation size allowance is explicit, confined and never changes public defaults", () => {
  const normal = audit(fixture());
  assert.equal(normal.status, 0, normal.stderr);
  assert.deepEqual(JSON.parse(normal.stdout).limits, {
    mode: "public_default", physicalBytes: 20 * 1024 * 1024,
    decodedJsonBytes: 128 * 1024 * 1024, publicViewerLimitsChanged: false,
  });
  const local = audit(fixture(), undefined, { local: true, args: ["--local-max-json-mib", "256"] });
  assert.equal(local.status, 0, local.stderr);
  assert.deepEqual(JSON.parse(local.stdout).limits, {
    mode: "explicit_local_only", physicalBytes: 256 * 1024 * 1024,
    decodedJsonBytes: 256 * 1024 * 1024, publicViewerLimitsChanged: false,
  });
  const outside = audit(fixture(), undefined, { args: ["--local-max-json-mib", "256"] });
  assert.notEqual(outside.status, 0);
  assert.match(outside.stderr, /inside this checkout's ignored local-runtime/);
  const arbitrary = audit(fixture(), undefined, { local: true, args: ["--local-max-json-mib", "512"] });
  assert.notEqual(arbitrary.status, 0);
  assert.match(arbitrary.stderr, /requires --local-max-json-mib 256/);
  const redirected = audit(fixture(), undefined, {
    local: true, args: ["--local-max-json-mib", "256"], redirectedRecording: true,
  });
  assert.notEqual(redirected.status, 0);
  assert.match(redirected.stderr, /recording must stay inside this checkout's ignored local-runtime/);
});

test("local presentation allowance retains red-crossing and metadata/schema rejection", () => {
  const options = { local: true, args: ["--local-max-json-mib", "256"] };
  const red = audit(fixture(true), undefined, options);
  assert.equal(red.status, 1);
  assert.equal(JSON.parse(red.stdout).results[0].worlds.afterlight.stats.allRedJunction, 1);
  const mismatch = audit(fixture(), entry => { entry.seed = 99; }, options);
  assert.notEqual(mismatch.status, 0);
  assert.match(mismatch.stderr, /does not match the selected experiment/);
  const invalid = audit({ schema: "afterlight.replay.v1" }, undefined, options);
  assert.notEqual(invalid.status, 0);
  assert.match(invalid.stderr, /supported recorded AFTERLIGHT run/);
});

test("local presentation allowance rejects a redirected runtime root in an isolated checkout", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "afterlight-audit-checkout-"));
  const external = fs.mkdtempSync(path.join(os.tmpdir(), "afterlight-audit-runtime-"));
  const web = path.join(directory, "web");
  const scripts = path.join(web, "scripts");
  const entrypoint = path.join(scripts, "audit-presentation.mjs");
  const sourceLink = path.join(web, "src");
  const runtimeLink = path.join(directory, "local-runtime");
  fs.mkdirSync(scripts, { recursive: true });
  try {
    fs.copyFileSync(fileURLToPath(new URL("../scripts/audit-presentation.mjs", import.meta.url)), entrypoint);
    const linkType = process.platform === "win32" ? "junction" : "dir";
    fs.symlinkSync(fileURLToPath(new URL("../src/", import.meta.url)), sourceLink, linkType);
    fs.symlinkSync(external, runtimeLink, linkType);
    const result = spawnSync(process.execPath, [
      "--experimental-strip-types", entrypoint,
      "--catalog", path.join(runtimeLink, "catalog.json"),
      "--local-max-json-mib", "256",
    ], { encoding: "utf8", timeout: 10000 });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /local-runtime must not redirect elsewhere/);
  } finally {
    // Only this isolated fixture's links and known copied file are removed.
    if (fs.existsSync(runtimeLink)) fs.unlinkSync(runtimeLink);
    if (fs.existsSync(sourceLink)) fs.unlinkSync(sourceLink);
    if (fs.existsSync(entrypoint)) fs.unlinkSync(entrypoint);
    fs.rmdirSync(scripts);
    fs.rmdirSync(web);
    fs.rmdirSync(directory);
    fs.rmdirSync(external);
  }
});

test("presentation physical bounds reject before JSON parsing in both modes", () => {
  const publicOversize = audit(fixture(), undefined, {
    physicalBytes: 20 * 1024 * 1024 + 1,
  });
  assert.notEqual(publicOversize.status, 0);
  assert.match(publicOversize.stderr, /Physical public recording exceeds 20 MiB/);
  const localOversize = audit(fixture(), undefined, {
    local: true, args: ["--local-max-json-mib", "256"],
    physicalBytes: 256 * 1024 * 1024 + 1,
  });
  assert.notEqual(localOversize.status, 0);
  assert.match(localOversize.stderr, /Physical local recording exceeds 256 MiB/);
  // The allowance passes the old physical ceiling; the unchanged byte binding
  // still rejects these deliberately padded, synthetic bytes before JSON parse.
  const localBinding = audit(fixture(), undefined, {
    local: true, args: ["--local-max-json-mib", "256"],
    physicalBytes: 20 * 1024 * 1024 + 1,
  });
  assert.notEqual(localBinding.status, 0);
  assert.match(localBinding.stderr, /length\/checksum differs/);
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
