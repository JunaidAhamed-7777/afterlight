import test from "node:test";
import assert from "node:assert/strict";
import { bindRecording } from "../src/recording.ts";
import type { CatalogEntry, Replay } from "../src/types.ts";
// Minimal metadata fixtures only: never traffic evidence or production recordings.
const entry: CatalogEntry = {
  id: "wanted",
  title: "Test fixture",
  url: "wanted.json",
  seed: 7,
  pickup_id: "P001",
  hospital_id: "HOSP_WEST",
  policy: "fixed",
  duration_s: 100,
};
const matching = () =>
  ({
    scenario: {
      id: "wanted",
      seed: 7,
      pickup_id: "P001",
      hospital_id: "HOSP_WEST",
    },
    duration_s: 100,
    worlds: { afterlight: { policy: "fixed" } },
  }) as unknown as Replay;
test("selected experiment metadata binds to the fetched artifact", () =>
  assert.equal(bindRecording(matching(), entry).scenario.id, "wanted"));
test("another valid scenario cannot silently replace a selected recording", () => {
  for (const patch of [
    { id: "other" },
    { seed: 8 },
    { pickup_id: "P002" },
    { hospital_id: "HOSP_EAST" },
  ]) {
    const r = matching();
    Object.assign(r.scenario, patch);
    assert.throws(() => bindRecording(r, entry), /does not match/);
  }
  const r = matching();
  r.worlds.afterlight.policy = "immediate";
  assert.throws(() => bindRecording(r, entry), /does not match/);
});

test("raw response byte count and checksum are verified before replay acceptance", async () => {
  const { loadRecording } = await import("../src/recording.ts");
  const original = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  try {
    await assert.rejects(
      loadRecording(
        { ...entry, bytes: 3 },
        "http://127.0.0.1/fixture",
        new AbortController().signal,
      ),
      /byte count/,
    );
    await assert.rejects(
      loadRecording(
        { ...entry, bytes: 2, sha256: "0".repeat(64) },
        "http://127.0.0.1/fixture",
        new AbortController().signal,
      ),
      /checksum/,
    );
  } finally {
    globalThis.fetch = original;
  }
});
test("checksum-verified structural fixture remains bound to selected metadata", async () => {
  const { loadRecording } = await import("../src/recording.ts");
  const frames = [
    { t: 0, vehicles: [], signals: [], queue_count: 0 },
    { t: 100, vehicles: [], signals: [], queue_count: 0 },
  ];
  const value = {
    schema: "afterlight.replay.v1",
    mode: "recorded",
    scenario: { ...entry, network_kind: "fixture", dispatch_s: 0 },
    coordinates: {
      source: "canonical XY meters",
      position_reference: "front_bumper",
      render: "[x,z,-y]",
    },
    provenance: {
      source_commit: "unit-fixture-only",
      network_sha256: "a".repeat(64),
      demand_sha256: "b".repeat(64),
      sumo_version: "no-simulator-executed",
    },
    duration_s: 100,
    step_s: 100,
    worlds: {
      afterlight: {
        world_id: "afterlight",
        policy: "fixed",
        status: "completed",
        metrics: {},
        events: [],
        frames,
      },
      baseline: {
        world_id: "baseline",
        policy: "ordinary",
        status: "completed",
        metrics: {},
        events: [],
        frames,
      },
    },
  };
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const hash = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0"),
  ).join("");
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(bytes, { status: 200 });
  try {
    const loaded = await loadRecording(
      { ...entry, bytes: bytes.byteLength, sha256: hash },
      "http://127.0.0.1/fixture",
      new AbortController().signal,
    );
    assert.equal(loaded.scenario.id, entry.id);
  } finally {
    globalThis.fetch = original;
  }
});

test("canonical policy binds separately from its human label and optional lead", () => {
  const r = matching();
  r.worlds.afterlight.lead_s = 10;
  assert.equal(bindRecording(r, {...entry, lead_s:10, policy_label:"fixed · 10 s lead"}), r);
  assert.throws(() => bindRecording(r, {...entry, lead_s:20}), /does not match/);
});
