import { boundedBytes } from "./response.ts";
import { parseJsonBytes } from "./strictJson.ts";

export const STUDY_MANIFEST_LIMIT = 16 * 1024;
export const STUDY_SUMMARY_LIMIT = 1024 * 1024;
const statuses = ["completed", "censored", "invalid", "infrastructure_error"] as const;
export type StudyStatusCounts = Record<(typeof statuses)[number], number>;
export interface StudyComparison {
  id: string;
  selected_label: string;
  comparator_label: string;
  episodes: number;
  demand_groups: number;
  paired_feasible_episodes: number;
  selected_failures: number;
  comparator_failures: number;
  selected_status_counts: StudyStatusCounts;
  comparator_status_counts: StudyStatusCounts;
  mean_delta_j_s: number | null;
  interval_95_j_s: [number, number] | null;
  interval_groups: number;
  interval_reason: string | null;
  changed_action_rate: number;
  mean_delta_ambulance_s: number | null;
  mean_delta_civilian_s: number | null;
}
export interface StudySummary {
  schema: "afterlight.study-summary.v1";
  status: "audited_released_test_evidence";
  mode: "learned" | "baseline_only";
  scope: "offline_cached_candidate_selection";
  automatic_benefit_claim: false;
  counts: { train: number; validation: number; test: number; test_worlds: number; test_demand_groups: number };
  holdouts: { regimes: string[]; route_families: string[] };
  objective: { civilian_weight: 1; definition: string };
  fixed_lead_s: number;
  comparisons: StudyComparison[];
  provenance: {
    source_commit: string;
    source_code_sha256: string;
    study_sha256: string;
    protocol_sha256: string;
    selection_sha256: string;
    release_sha256: string;
    test_attempt_sha256: string;
    report_sha256: string;
    report_file_sha256: string;
    model_sha256: string | null;
  };
  artifacts: Array<{ kind: string; url: string; sha256: string; bytes: number }>;
}
export interface StudyManifest {
  schema: "afterlight.study-summary-manifest.v1";
  url: "summary.json";
  sha256: string;
  bytes: number;
}
export interface LoadedStudy {
  summary: StudySummary;
  manifest: StudyManifest;
  manifestUrl: string;
  summaryUrl: string;
}
export class StudyUnpublishedError extends Error {
  constructor() {
    super("An audited study has not been published in this build.");
    this.name = "StudyUnpublishedError";
  }
}

function fail(field: string): never {
  throw new Error(`The study evidence could not be verified (${field}). Retry the study.`);
}
function object(value: unknown, field: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(field);
  return value as Record<string, unknown>;
}
function keys(value: Record<string, unknown>, expected: string[], field: string) {
  if (Object.keys(value).length !== expected.length || expected.some(key => !Object.hasOwn(value, key))) fail(field);
}
function text(value: unknown, field: string, max = 200): asserts value is string {
  if (typeof value !== "string" || !value.trim() || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) fail(field);
}
function count(value: unknown, field: string, positive = false): asserts value is number {
  if (!Number.isSafeInteger(value) || (value as number) < (positive ? 1 : 0)) fail(field);
}
function finite(value: unknown, field: string): asserts value is number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail(field);
}
function hash(value: unknown, field: string) {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value)) fail(field);
}
/** Local artifact names only; no URL decoding, traversal, query or fragment aliases. */
export function studyArtifactUrl(relative: string, summaryUrl: string): string {
  if (!/^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*(?:\/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)*$/.test(relative))
    fail("local artifact path");
  const base = new URL(summaryUrl);
  const result = new URL(relative, base);
  if (!["http:", "https:"].includes(base.protocol) || base.username || base.password || result.origin !== base.origin)
    fail("artifact origin");
  return result.href;
}
function stringList(value: unknown, field: string) {
  if (!Array.isArray(value) || value.length > 512) fail(field);
  for (const item of value) text(item, field, 200);
  if (new Set(value).size !== value.length) fail(field);
}
function statusCounts(value: unknown, episodes: number, failures: number, field: string) {
  const row = object(value, field);
  keys(row, [...statuses], field);
  for (const status of statuses) count(row[status], field);
  const counts = row as StudyStatusCounts;
  if (statuses.reduce((sum, status) => sum + counts[status], 0) !== episodes ||
      failures < episodes - counts.completed || counts.infrastructure_error !== 0) fail(field);
}
export function validateStudyManifest(value: unknown): StudyManifest {
  const manifest = object(value, "manifest");
  keys(manifest, ["schema", "url", "sha256", "bytes"], "manifest fields");
  if (manifest.schema !== "afterlight.study-summary-manifest.v1" || manifest.url !== "summary.json") fail("manifest schema or URL");
  hash(manifest.sha256, "manifest checksum");
  count(manifest.bytes, "manifest byte count", true);
  if (manifest.bytes > STUDY_SUMMARY_LIMIT) fail("summary size");
  return manifest as unknown as StudyManifest;
}
export function validateStudySummary(value: unknown): StudySummary {
  const summary = object(value, "summary");
  keys(summary, ["schema", "status", "mode", "scope", "automatic_benefit_claim", "counts", "holdouts", "objective", "fixed_lead_s", "comparisons", "provenance", "artifacts"], "summary fields");
  if (summary.schema !== "afterlight.study-summary.v1" || summary.status !== "audited_released_test_evidence" ||
      (summary.mode !== "learned" && summary.mode !== "baseline_only") || summary.scope !== "offline_cached_candidate_selection" ||
      summary.automatic_benefit_claim !== false) fail("release scope");
  const counts = object(summary.counts, "split counts");
  keys(counts, ["train", "validation", "test", "test_worlds", "test_demand_groups"], "split counts");
  for (const value of Object.values(counts)) count(value, "split count", true);
  const n = counts.test as number, groups = counts.test_demand_groups as number;
  if (counts.test_worlds !== n * 7 || groups > n) fail("test coverage");
  const holdouts = object(summary.holdouts, "holdouts");
  keys(holdouts, ["regimes", "route_families"], "holdouts");
  stringList(holdouts.regimes, "held-out regimes");
  stringList(holdouts.route_families, "held-out route families");
  const objective = object(summary.objective, "objective");
  keys(objective, ["civilian_weight", "definition"], "objective fields");
  if (objective.civilian_weight !== 1) fail("civilian objective weight");
  text(objective.definition, "objective definition", 2000);
  if (![0, 5, 10, 20, 30].includes(summary.fixed_lead_s as number)) fail("fixed lead");
  const expectedComparisons = summary.mode === "learned"
    ? ["learned-vs-fixed", "learned-vs-analytical"]
    : ["analytical-vs-fixed"];
  if (!Array.isArray(summary.comparisons) || summary.comparisons.length !== expectedComparisons.length) fail("comparisons");
  const ids = new Set<string>();
  const comparatorLabels = new Set<string>();
  for (const [index, input] of summary.comparisons.entries()) {
    const row = object(input, "comparison");
    keys(row, ["id", "selected_label", "comparator_label", "episodes", "demand_groups", "paired_feasible_episodes", "selected_failures", "comparator_failures", "selected_status_counts", "comparator_status_counts", "mean_delta_j_s", "interval_95_j_s", "interval_groups", "interval_reason", "changed_action_rate", "mean_delta_ambulance_s", "mean_delta_civilian_s"], "comparison fields");
    text(row.id, "comparison ID");
    text(row.selected_label, "selected label");
    text(row.comparator_label, "comparator label");
    if (row.id !== expectedComparisons[index] || ids.has(row.id) || comparatorLabels.has(row.comparator_label)) fail("comparison identity or order");
    ids.add(row.id); comparatorLabels.add(row.comparator_label);
    for (const field of ["episodes", "demand_groups", "paired_feasible_episodes", "selected_failures", "comparator_failures", "interval_groups"])
      count(row[field], field);
    const comparison = row as unknown as StudyComparison;
    if (comparison.episodes !== n || comparison.demand_groups !== groups ||
        comparison.selected_failures > n || comparison.comparator_failures > n ||
        comparison.paired_feasible_episodes < Math.max(0, n - comparison.selected_failures - comparison.comparator_failures) ||
        comparison.paired_feasible_episodes > Math.min(n - comparison.selected_failures, n - comparison.comparator_failures) ||
        comparison.interval_groups > Math.min(groups, comparison.paired_feasible_episodes) ||
        (comparison.paired_feasible_episodes > 0 && comparison.interval_groups === 0)) fail("paired comparison coverage");
    statusCounts(row.selected_status_counts, n, comparison.selected_failures, "selected status counts");
    statusCounts(row.comparator_status_counts, n, comparison.comparator_failures, "comparator status counts");
    finite(row.changed_action_rate, "changed action rate");
    if (row.changed_action_rate < 0 || row.changed_action_rate > 1) fail("changed action rate");
    for (const field of ["mean_delta_j_s", "mean_delta_ambulance_s", "mean_delta_civilian_s"]) {
      if (comparison.paired_feasible_episodes === 0) {
        if (row[field] !== null) fail("unavailable paired mean");
      } else finite(row[field], field);
    }
    if (comparison.paired_feasible_episodes > 0) {
      const total = comparison.mean_delta_ambulance_s! + comparison.mean_delta_civilian_s!;
      if (!Number.isFinite(total) || Math.abs(total - comparison.mean_delta_j_s!) > 1e-7 * Math.max(1, Math.abs(total), Math.abs(comparison.mean_delta_j_s!))) fail("objective delta agreement");
    }
    if (comparison.interval_groups < 10) {
      if (row.interval_95_j_s !== null) fail("unsupported confidence interval");
      text(row.interval_reason, "unavailable interval reason", 1000);
    } else {
      if (!Array.isArray(row.interval_95_j_s) || row.interval_95_j_s.length !== 2 || row.interval_reason !== null) fail("confidence interval");
      const [low, high] = row.interval_95_j_s;
      finite(low, "confidence interval lower bound"); finite(high, "confidence interval upper bound");
      if (low > high) fail("confidence interval order");
    }
  }
  const provenance = object(summary.provenance, "provenance");
  keys(provenance, ["source_commit", "source_code_sha256", "study_sha256", "protocol_sha256", "selection_sha256", "release_sha256", "test_attempt_sha256", "report_sha256", "report_file_sha256", "model_sha256"], "provenance fields");
  if (typeof provenance.source_commit !== "string" || !/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(provenance.source_commit)) fail("source commit");
  for (const [field, value] of Object.entries(provenance)) {
    if (field === "source_commit") continue;
    if (field === "model_sha256" && summary.mode === "baseline_only") {
      if (value !== null) fail("baseline-only model identity");
    } else hash(value, field);
  }
  if (!Array.isArray(summary.artifacts) || !summary.artifacts.length || summary.artifacts.length > 128) fail("artifact inventory");
  const paths = new Set<string>();
  const artifactsByKind = new Map<string, Record<string, unknown>>();
  for (const input of summary.artifacts) {
    const artifact = object(input, "artifact");
    keys(artifact, ["kind", "url", "sha256", "bytes"], "artifact fields");
    text(artifact.kind, "artifact kind"); text(artifact.url, "artifact URL", 300);
    studyArtifactUrl(artifact.url, "https://study.invalid/study/summary.json");
    if (paths.has(artifact.url) || artifactsByKind.has(artifact.kind)) fail("duplicate artifact identity");
    paths.add(artifact.url);
    artifactsByKind.set(artifact.kind, artifact);
    hash(artifact.sha256, "artifact checksum"); count(artifact.bytes, "artifact byte count", true);
  }
  if (artifactsByKind.get("report")?.sha256 !== provenance.report_file_sha256) fail("report artifact binding");
  if (summary.mode === "learned") {
    if (artifactsByKind.get("model")?.sha256 !== provenance.model_sha256) fail("model artifact binding");
  } else if (artifactsByKind.has("model")) fail("baseline-only model artifact");
  return summary as unknown as StudySummary;
}

/** Mount-owned caller supplies cancellation; no cache, eager request or test artifact fallback. */
export async function loadStudySummary(manifestUrl: string, signal: AbortSignal): Promise<LoadedStudy> {
  signal.throwIfAborted();
  const request = async (url: string, limit: number, manifest = false) => {
    const resource = manifest ? "manifest" : "summary";
    const requestSignal = AbortSignal.any([signal, AbortSignal.timeout(15000)]);
    try {
      const response = await fetch(url, {
        signal: requestSignal,
        cache: "no-cache",
        redirect: "error",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        await response.body?.cancel();
        if (manifest && response.status === 404) throw new StudyUnpublishedError();
        throw new Error(`Study ${resource} request failed (${response.status}). Retry the study.`);
      }
      const bytes = await boundedBytes(response, limit);
      signal.throwIfAborted();
      return bytes;
    } catch (error) {
      // A user leaving the view remains cancellation, not a publication error.
      signal.throwIfAborted();
      if ((error instanceof Error && error.name === "TimeoutError") || requestSignal.reason?.name === "TimeoutError")
        throw new Error(`The study ${resource} request timed out. Retry the study.`);
      if (error instanceof Error && /size limit/.test(error.message))
        throw new Error(`The study ${resource} exceeds its ${manifest ? "16 KiB" : "1 MiB"} size limit. Retry after the publication is corrected.`);
      throw error;
    }
  };
  const parse = (bytes: Uint8Array, limit: number, resource: "manifest" | "summary") => {
    try { return parseJsonBytes(bytes, limit); }
    catch (error) {
      const detail = error instanceof Error && /UTF-8/.test(error.message) ? "could not be read as UTF-8 JSON"
        : error instanceof Error && /nonfinite/.test(error.message) ? "contains invalid numbers" : "is not valid JSON";
      throw new Error(`The study ${resource} ${detail}. Retry after the publication is corrected.`);
    }
  };
  const manifest = validateStudyManifest(parse(await request(manifestUrl, STUDY_MANIFEST_LIMIT, true), STUDY_MANIFEST_LIMIT, "manifest"));
  const summaryUrl = studyArtifactUrl(manifest.url, manifestUrl);
  const bytes = await request(summaryUrl, STUDY_SUMMARY_LIMIT);
  if (bytes.byteLength !== manifest.bytes) throw new Error("The study summary byte count does not match its manifest. Retry after the publication completes.");
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  signal.throwIfAborted();
  const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  if (sha256 !== manifest.sha256) throw new Error("The study summary checksum does not match its manifest. Retry after the publication completes.");
  return { manifest, summary: validateStudySummary(parse(bytes, STUDY_SUMMARY_LIMIT, "summary")), manifestUrl, summaryUrl };
}
