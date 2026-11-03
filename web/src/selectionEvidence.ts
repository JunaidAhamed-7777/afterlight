import type { Replay, SelectionEvidence } from "./types.ts";
const object = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);
const nonempty = (value: unknown): value is string => typeof value === "string" && value.length > 0;
const hash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);

/** Bind optional offline selection provenance without rewriting recorded physics. */
export function validateSelectionEvidence(replay: Replay): void {
  const evidence = replay.selection_evidence;
  if (evidence == null) return;
  if (!object(evidence) || evidence.schema !== "afterlight.selection-evidence.v1" ||
      !["residual_tree", "analytical"].includes(evidence.selector_kind))
    throw new Error("Unsupported offline selection evidence.");
  for (const field of ["selector_sha256", "study_sha256", "protocol_sha256", "release_sha256", "report_sha256",
    "selection_sha256", "trace_manifest_sha256", "collection_manifest_sha256", "comparison_artifact_sha256"] as const)
    if (!hash(evidence[field])) throw new Error("Offline selection evidence is missing artifact hashes.");
  for (const field of ["model_sha256", "model_file_sha256"] as const)
    if (evidence.selector_kind === "residual_tree" ? !hash(evidence[field]) : evidence[field] != null)
      throw new Error("Model identity does not match the offline selector kind.");
  if ((replay.provenance.model_sha256 ?? null) !== (evidence.model_sha256 ?? null))
    throw new Error("Replay and offline selection model identities differ.");
  const lead = evidence.selected_lead_s;
  const world = replay.worlds.afterlight;
  if (![0, 5, 10, 20, 30].includes(lead) || world.policy !== "fixed" || world.lead_s !== lead)
    throw new Error("Offline selection must preserve its recorded fixed-lead physics.");
  const decision = world.decision;
  if (!object(decision) || decision.policy !== "fixed" || decision.selected_lead_s !== lead ||
      decision.kind !== "dispatch" || decision.t !== replay.scenario.dispatch_s)
    throw new Error("Offline selection must preserve the frozen fixed-policy dispatch decision.");
  if (!nonempty(evidence.episode_id) || evidence.episode_id !== replay.scenario.episode_id || replay.scenario.split !== "test")
    throw new Error("Offline selection episode or split does not match the recording.");
  if (typeof evidence.case_id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(evidence.case_id))
    throw new Error("Offline selection has an invalid predeclared case identity.");
  const aliases = evidence.source_world_aliases;
  if (!object(aliases) || Object.keys(aliases).sort().join(",") !== "afterlight,baseline")
    throw new Error("Offline selection needs explicit original-world aliases.");
  for (const alias of ["baseline", "afterlight"] as const) {
    const source = aliases[alias];
    const expected = `worlds/${evidence.case_id}/${alias === "baseline" ? "ordinary" : `fixed-${lead}`}/rich-world.json`;
    if (!object(source) || !nonempty(source.original_world_id) || !hash(source.trace_sha256) || source.trace_file !== expected)
      throw new Error("Offline selection has an invalid retained trace identity or path.");
  }
  if (!nonempty(evidence.interpretation)) throw new Error("Offline selection interpretation is missing.");
}
export function selectionLabel(evidence: SelectionEvidence): string {
  const selector = evidence.selector_kind === "residual_tree" ? "Learned selector" : "Analytical selector";
  return `${selector} · recorded fixed ${evidence.selected_lead_s} s candidate`;
}
