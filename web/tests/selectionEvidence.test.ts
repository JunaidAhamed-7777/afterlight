import test from "node:test";
import assert from "node:assert/strict";
import { validateReplay } from "../src/replay.ts";
import { selectionLabel } from "../src/selectionEvidence.ts";
import type { Replay, SelectionEvidence } from "../src/types.ts";
import { structuralReplay } from "./fixtures/structuralReplay.ts";
const hash = "c".repeat(64);
function selected(kind: "residual_tree" | "analytical" = "residual_tree"): Replay {
  const replay = structuralReplay();
  replay.scenario.episode_id = "episode-unit"; replay.scenario.split = "test";
  replay.worlds.afterlight.lead_s = 10;
  replay.worlds.afterlight.decision = { kind: "dispatch", policy: "fixed", selected_lead_s: 10, t: 0, request_plan: {} };
  replay.provenance.model_sha256 = kind === "residual_tree" ? hash : null;
  replay.selection_evidence = {
    schema: "afterlight.selection-evidence.v1", selector_kind: kind,
    selector_sha256: hash, study_sha256: hash, protocol_sha256: hash, release_sha256: hash, report_sha256: hash,
    selection_sha256: hash, trace_manifest_sha256: hash, collection_manifest_sha256: hash, comparison_artifact_sha256: hash,
    model_sha256: kind === "residual_tree" ? hash : null, model_file_sha256: kind === "residual_tree" ? hash : null,
    case_id: "case-unit", episode_id: "episode-unit", selected_lead_s: 10,
    source_world_aliases: {
      baseline: { original_world_id: "ordinary", trace_sha256: hash, trace_file: "worlds/case-unit/ordinary/rich-world.json" },
      afterlight: { original_world_id: "fixed-10", trace_sha256: hash, trace_file: "worlds/case-unit/fixed-10/rich-world.json" },
    }, interpretation: "Synthetic structure only. No trained model, simulation or gain is claimed.",
  };
  return replay;
}
test("optional evidence preserves legacy v1 and explicit analytical null models", () => {
  assert.equal(validateReplay(structuralReplay()).selection_evidence, undefined);
  const analytical = selected("analytical"); assert.equal(validateReplay(analytical), analytical);
  assert.equal(selectionLabel(analytical.selection_evidence!), "Analytical selector · recorded fixed 10 s candidate");
});
test("learned label distinguishes offline selection from recorded fixed physics", () => {
  const replay = selected(); const before = JSON.stringify(replay.worlds);
  validateReplay(replay);
  assert.equal(selectionLabel(replay.selection_evidence!), "Learned selector · recorded fixed 10 s candidate");
  assert.equal(JSON.stringify(replay.worlds), before);
  assert.equal(replay.worlds.afterlight.policy, "fixed");
});
test("selected invalid or censored outcomes are never promoted by evidence", () => {
  for (const status of ["invalid", "censored"]) {
    const replay = selected(); replay.worlds.afterlight.status = status;
    assert.equal(validateReplay(replay).worlds.afterlight.status, status);
  }
});
test("wrong model, physical lead, decision and missing episode binding reject", () => {
  const mutations: Array<(replay: Replay) => void> = [
    r => { r.provenance.model_sha256 = null; },
    r => { r.worlds.afterlight.policy = "learned"; },
    r => { r.worlds.afterlight.lead_s = 20; },
    r => { r.worlds.afterlight.decision!.selected_lead_s = 20; },
    r => { r.worlds.afterlight.decision!.t = 1; },
    r => { delete r.scenario.episode_id; delete (r.selection_evidence as Partial<SelectionEvidence>).episode_id; },
    r => { r.scenario.split = "validation"; },
    r => { r.selection_evidence!.model_file_sha256 = null; },
  ];
  for (const mutate of mutations) { const replay = selected(); mutate(replay); assert.throws(() => validateReplay(replay)); }
  const analytical = selected("analytical"); analytical.selection_evidence!.model_sha256 = hash;
  assert.throws(() => validateReplay(analytical), /selector kind/);
});
test("all provenance hashes and exact local trace aliases are required", () => {
  for (const key of ["selector_sha256", "study_sha256", "protocol_sha256", "release_sha256", "report_sha256", "selection_sha256",
    "trace_manifest_sha256", "collection_manifest_sha256", "comparison_artifact_sha256"] as const) {
    const replay = selected(); replay.selection_evidence![key] = "not-a-hash";
    assert.throws(() => validateReplay(replay), /artifact hashes/);
  }
  for (const path of ["https://example.invalid/trace", "../trace", "worlds/case-unit/fixed-20/rich-world.json", "C:\\trace.json"]) {
    const replay = selected(); replay.selection_evidence!.source_world_aliases.afterlight.trace_file = path;
    assert.throws(() => validateReplay(replay), /trace identity or path/);
  }
});
