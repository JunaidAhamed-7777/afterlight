import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  loadStudySummary,
  studyArtifactUrl,
  StudyUnpublishedError,
  STUDY_MANIFEST_LIMIT,
  STUDY_SUMMARY_LIMIT,
  validateStudyManifest,
  validateStudySummary,
  type StudySummary,
} from "../src/studySummary.ts";

// SYNTHETIC UNIT DATA ONLY. No simulator ran; these are never published study evidence.
const digest = (value: Uint8Array) => createHash("sha256").update(value).digest("hex");
function fixture(): StudySummary {
  const comparison = {
    id: "learned-vs-fixed", selected_label: "Synthetic selector", comparator_label: "Synthetic tuned fixed",
    episodes: 20, demand_groups: 12, paired_feasible_episodes: 18,
    selected_failures: 1, comparator_failures: 1,
    selected_status_counts: { completed: 19, censored: 1, invalid: 0, infrastructure_error: 0 },
    comparator_status_counts: { completed: 20, censored: 0, invalid: 0, infrastructure_error: 0 },
    mean_delta_j_s: 3, interval_95_j_s: [-2, 8] as [number, number], interval_groups: 11,
    interval_reason: null, changed_action_rate: .25, mean_delta_ambulance_s: -4, mean_delta_civilian_s: 7,
  };
  return {
    schema: "afterlight.study-summary.v1", status: "audited_released_test_evidence", mode: "learned",
    scope: "offline_cached_candidate_selection", automatic_benefit_claim: false,
    counts: { train: 40, validation: 20, test: 20, test_worlds: 140, test_demand_groups: 12 },
    holdouts: { regimes: ["synthetic-regime"], route_families: ["synthetic-route"] },
    objective: { civilian_weight: 1, definition: "Synthetic objective: ambulance journey plus mean civilian excess time." },
    fixed_lead_s: 20,
    comparisons: [comparison, { ...structuredClone(comparison), id: "learned-vs-analytical", comparator_label: "Synthetic analytical" }],
    provenance: {
      source_commit: "a".repeat(40), source_code_sha256: "a".repeat(64), study_sha256: "b".repeat(64),
      protocol_sha256: "c".repeat(64), selection_sha256: "d".repeat(64), release_sha256: "e".repeat(64),
      test_attempt_sha256: "f".repeat(64), report_sha256: "1".repeat(64), report_file_sha256: "2".repeat(64), model_sha256: "3".repeat(64),
    },
    artifacts: [{ kind: "report", url: "report.json", sha256: "2".repeat(64), bytes: 123 },
      { kind: "model", url: "model.json", sha256: "3".repeat(64), bytes: 321 }],
  };
}
const manifestUrl = "https://unit.invalid/app/study/manifest.json";
const encode = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));
function packed(value: unknown = fixture()) {
  const bytes = encode(value);
  return { bytes, manifest: { schema: "afterlight.study-summary-manifest.v1", url: "summary.json", sha256: digest(bytes), bytes: bytes.length } };
}
async function mockedFetch(run: (calls: Array<{ url: string; options?: RequestInit }>) => Promise<void>, handler: (url: string, options?: RequestInit) => Response | Promise<Response>) {
  const original = globalThis.fetch;
  const calls: Array<{ url: string; options?: RequestInit }> = [];
  globalThis.fetch = async (input, options) => {
    const url = String(input);
    calls.push({ url, options });
    return handler(url, options);
  };
  try { await run(calls); } finally { globalThis.fetch = original; }
}

test("released summary preserves unfavorable deltas, status failures and uncertainty without inventing benefit", () => {
  const value = fixture(), original = structuredClone(value);
  assert.equal(validateStudySummary(value), value);
  assert.equal(value.comparisons[0].mean_delta_j_s, 3);
  assert.equal(value.comparisons[0].mean_delta_ambulance_s, -4);
  assert.equal(value.comparisons[0].mean_delta_civilian_s, 7);
  assert.deepEqual(value, original);
  // A completed world can lack an objective; failure counts are not merely status counts.
  assert.equal(value.comparisons[0].comparator_status_counts.completed, 20);
  assert.equal(value.comparisons[0].comparator_failures, 1);
});

test("baseline-only publication contains exactly its analytical-vs-fixed comparison and no learned model", () => {
  const value = fixture(); value.mode = "baseline_only"; value.provenance.model_sha256 = null;
  value.comparisons = [{ ...value.comparisons[0], id: "analytical-vs-fixed", selected_label: "Synthetic analytical" }];
  value.artifacts = value.artifacts.filter(artifact => artifact.kind !== "model");
  assert.equal(validateStudySummary(value).mode, "baseline_only");
  value.provenance.model_sha256 = "a".repeat(64);
  assert.throws(() => validateStudySummary(value), /baseline-only model/);
});

test("declared protocols may have no regime or route-family holdouts without inventing names", () => {
  const value = fixture(); value.holdouts = { regimes: [], route_families: [] };
  assert.deepEqual(validateStudySummary(value).holdouts, { regimes: [], route_families: [] });
});

test("both Git identity lengths are retained without converting source bytes", () => {
  const value = fixture(); value.provenance.source_commit = "b".repeat(64);
  assert.equal(validateStudySummary(value).provenance.source_commit.length, 64);
});

test("the paired feasible count cannot silently exclude complete finite pairs", () => {
  const value = fixture();
  for (const row of value.comparisons) {
    row.selected_failures = row.comparator_failures = 0;
    row.selected_status_counts = row.comparator_status_counts = { completed: 20, censored: 0, invalid: 0, infrastructure_error: 0 };
    row.paired_feasible_episodes = 10; row.interval_groups = 10;
  }
  assert.throws(() => validateStudySummary(value), /paired comparison coverage/);
});

test("artifact kinds and exact report/model file hashes bind published provenance", () => {
  const changes: Array<(value: StudySummary) => void> = [
    value => { value.artifacts[0].sha256 = "f".repeat(64); },
    value => { value.artifacts[1].sha256 = "f".repeat(64); },
    value => { value.artifacts[0].kind = "unbound_report"; },
    value => { value.artifacts[1].kind = "unbound_model"; },
    value => { value.artifacts.push({ ...value.artifacts[0], url: "other-report.json" }); },
  ];
  for (const mutate of changes) { const value = fixture(); mutate(value); assert.throws(() => validateStudySummary(value)); }
});

test("no eligible pairs retain null means and a reason instead of zero-valued results", () => {
  const value = fixture();
  for (const row of value.comparisons) {
    row.selected_failures = 20; row.paired_feasible_episodes = 0; row.interval_groups = 0;
    row.mean_delta_j_s = row.mean_delta_ambulance_s = row.mean_delta_civilian_s = null;
    row.interval_95_j_s = null; row.interval_reason = "Synthetic: no paired finite objective.";
  }
  validateStudySummary(value);
  value.comparisons[0].mean_delta_j_s = 0;
  assert.throws(() => validateStudySummary(value), /unavailable paired mean/);
});

test("confidence bounds require ten independent groups and an explicit reason when unavailable", () => {
  const value = fixture(), row = value.comparisons[0];
  row.interval_groups = 9; row.interval_95_j_s = null; row.interval_reason = "Synthetic: fewer than ten independent groups.";
  validateStudySummary(value);
  row.interval_reason = "";
  assert.throws(() => validateStudySummary(value), /reason/);
  row.interval_reason = "Synthetic reason"; row.interval_95_j_s = [-3, 4];
  assert.throws(() => validateStudySummary(value), /unsupported confidence interval/);
  row.interval_groups = 10; row.interval_reason = null; row.interval_95_j_s = [4, 8];
  validateStudySummary(value); // An interval need not contain the observed mean.
  row.interval_95_j_s = [8, 4];
  assert.throws(() => validateStudySummary(value), /order/);
});

test("release, split, paired-population, finite metrics and provenance inconsistencies fail closed", () => {
  const mutations: Array<(value: StudySummary) => void> = [
    value => { (value as unknown as Record<string, unknown>).status = "pending"; },
    value => { (value as unknown as Record<string, unknown>).automatic_benefit_claim = true; },
    value => { (value as unknown as Record<string, unknown>).scope = "live_inference"; },
    value => { value.counts.train = 0; }, value => { value.counts.test = 1.5; },
    value => { value.counts.test_worlds--; }, value => { value.counts.test_demand_groups = 21; },
    value => { value.holdouts.route_families.push("synthetic-route"); },
    value => { value.fixed_lead_s = 12; }, value => { value.comparisons[0].episodes--; },
    value => { value.comparisons[0].demand_groups--; }, value => { value.comparisons[0].paired_feasible_episodes = 20; },
    value => { value.comparisons[0].selected_failures = 0; },
    value => { value.comparisons[0].selected_status_counts.completed--; },
    value => { value.comparisons[0].selected_status_counts.completed--; value.comparisons[0].selected_status_counts.infrastructure_error++; },
    value => { value.comparisons[0].interval_groups = 19; }, value => { value.comparisons[0].interval_groups = 0; },
    value => { value.comparisons[0].mean_delta_j_s = null; }, value => { value.comparisons[0].mean_delta_civilian_s = Infinity; },
    value => { value.comparisons[0].mean_delta_j_s = 4; }, value => { value.comparisons[0].changed_action_rate = -.1; },
    value => { value.comparisons[0].changed_action_rate = NaN; }, value => { value.comparisons.reverse(); },
    value => { value.comparisons[1].id = value.comparisons[0].id; }, value => { value.comparisons.pop(); },
    value => { value.provenance.source_commit = "uncommitted"; }, value => { value.provenance.report_file_sha256 = "f"; },
    value => { value.provenance.model_sha256 = null; }, value => { value.artifacts[0].bytes = -1; },
    value => { value.artifacts.push(structuredClone(value.artifacts[0])); },
    value => { (value as unknown as Record<string, unknown>).mode = ["learned"]; },
    value => { value.comparisons[0].mean_delta_ambulance_s = 1e308; value.comparisons[0].mean_delta_civilian_s = 1e308; },
  ];
  for (const mutate of mutations) {
    const value = fixture(); mutate(value);
    assert.throws(() => validateStudySummary(value), undefined, String(mutate));
  }
});

test("artifact URLs remain beneath the local study directory without ambiguous aliases", () => {
  assert.equal(studyArtifactUrl("exports/test-report.json", manifestUrl), "https://unit.invalid/app/study/exports/test-report.json");
  for (const url of ["../report.json", "x/../report.json", "x/./report.json", "/report.json", "//other.invalid/report", "https://other.invalid/report", "javascript:alert(1)", "data:text/plain,x", "x\\report.json", "%2e%2e/report.json", "report.json?q=x", "report.json#x"]) {
    const value = fixture(); value.artifacts[0].url = url;
    assert.throws(() => validateStudySummary(value), /artifact path/);
  }
});

test("manifest rejects path substitution, missing integrity, extra fields and excessive publication size", () => {
  const { manifest } = packed(); validateStudyManifest(manifest);
  for (const patch of [{ url: "../summary.json" }, { url: "other.json" }, { sha256: null }, { bytes: 0 }, { bytes: STUDY_SUMMARY_LIMIT + 1 }, { extra: true }])
    assert.throws(() => validateStudyManifest({ ...manifest, ...patch }));
});

test("loader requests only manifest then exact summary bytes, preserves subpath, and sends abortable no-cache requests", async () => {
  const { manifest, bytes } = packed();
  await mockedFetch(async calls => {
    const result = await loadStudySummary(manifestUrl, new AbortController().signal);
    assert.equal(result.summary.mode, "learned"); assert.equal(result.manifest.sha256, digest(bytes));
    assert.equal(result.summaryUrl, "https://unit.invalid/app/study/summary.json");
    assert.deepEqual(calls.map(row => row.url), [manifestUrl, result.summaryUrl]);
    for (const row of calls) {
      assert.equal(row.options?.cache, "no-cache"); assert.equal(row.options?.redirect, "error");
      assert.equal(new Headers(row.options?.headers).get("Accept"), "application/json");
      assert.ok(row.options?.signal instanceof AbortSignal);
    }
  }, url => new Response(url === manifestUrl ? encode(manifest) : bytes));
});

test("unpublished manifest 404 differs from a broken published summary or server failure", async () => {
  await mockedFetch(async calls => {
    await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal), StudyUnpublishedError);
    assert.equal(calls.length, 1);
  }, () => new Response(null, { status: 404 }));
  const { manifest } = packed();
  await mockedFetch(async () => {
    await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal), /summary request failed \(404\)/);
  }, url => new Response(url === manifestUrl ? encode(manifest) : null, { status: url === manifestUrl ? 200 : 404 }));
  await mockedFetch(async () => {
    await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal), /manifest request failed \(503\)/);
  }, () => new Response(null, { status: 503 }));
});

test("a malformed HTML success response is a publication error, never an unpublished marker", async () => {
  await mockedFetch(async () => {
    await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal), error => !(error instanceof StudyUnpublishedError));
  }, () => new Response("<!doctype html><title>Unit SPA fallback</title>", { headers: { "Content-Type": "text/html" } }));
});

test("malformed study JSON uses concise resource-specific copy without native parser locations", async () => {
  const malformed = new TextEncoder().encode('{"synthetic-unit-only": }');
  for (const resource of ["manifest", "summary"] as const) {
    const manifest = { schema: "afterlight.study-summary-manifest.v1", url: "summary.json", sha256: digest(malformed), bytes: malformed.length };
    await mockedFetch(async () => {
      await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal), error => {
        assert.ok(error instanceof Error);
        assert.equal(error.message, `The study ${resource} is not valid JSON. Retry after the publication is corrected.`);
        assert.doesNotMatch(error.message, /position|column|line\s+\d|Unexpected|synthetic-unit-only/);
        return true;
      });
    }, url => new Response(resource === "summary" && url === manifestUrl ? encode(manifest) : malformed));
  }
});

test("invalid study encoding and numbers have readable study-specific recovery copy", async () => {
  for (const [bytes, detail] of [
    [new Uint8Array([0xff]), "could not be read as UTF-8 JSON"],
    [new TextEncoder().encode('{"synthetic-unit-only":1e400}'), "contains invalid numbers"],
  ] as const) {
    const manifest = { schema: "afterlight.study-summary-manifest.v1", url: "summary.json", sha256: digest(bytes), bytes: bytes.length };
    await mockedFetch(async () => {
      await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal), {
        message: `The study summary ${detail}. Retry after the publication is corrected.`,
      });
    }, url => new Response(url === manifestUrl ? encode(manifest) : bytes));
  }
});

test("timed-out study requests identify the resource and offer retry", async () => {
  const { manifest } = packed();
  for (const resource of ["manifest", "summary"] as const) {
    await mockedFetch(async () => {
      await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal), {
        message: `The study ${resource} request timed out. Retry the study.`,
      });
    }, url => {
      if (resource === "summary" && url === manifestUrl) return new Response(encode(manifest));
      throw new DOMException("Synthetic native timeout detail must not appear", "TimeoutError");
    });
  }
});

test("checksum and byte count reject changed summary bytes before acceptance", async () => {
  for (const mismatch of ["bytes", "checksum"] as const) {
    const { manifest, bytes } = packed();
    if (mismatch === "bytes") manifest.bytes--; else manifest.sha256 = "0".repeat(64);
    await mockedFetch(async () => {
      await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal), mismatch === "bytes" ? /byte count/ : /checksum/);
    }, url => new Response(url === manifestUrl ? encode(manifest) : bytes));
  }
});

test("manifest and summary streams are bounded even without Content-Length", async () => {
  for (const target of ["manifest", "summary"] as const) {
    const { manifest } = packed(); let canceled = false;
    const limit = target === "manifest" ? STUDY_MANIFEST_LIMIT : STUDY_SUMMARY_LIMIT;
    await mockedFetch(async () => {
      await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal), {
        message: `The study ${target} exceeds its ${target === "manifest" ? "16 KiB" : "1 MiB"} size limit. Retry after the publication is corrected.`,
      });
      assert.equal(canceled, true);
    }, url => {
      if (target === "summary" && url === manifestUrl) return new Response(encode(manifest));
      return new Response(new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(limit + 1)); }, cancel() { canceled = true; } }));
    });
  }
});

test("invalid UTF-8, overflow numbers and structurally wrong but hash-matching summaries fail", async () => {
  for (const bytes of [new Uint8Array([0xff]), new TextEncoder().encode('{"overflow":1e400}'), encode({ schema: "afterlight.study-summary.v1", status: "pending" })]) {
    const manifest = { schema: "afterlight.study-summary-manifest.v1", url: "summary.json", sha256: digest(bytes), bytes: bytes.length };
    await mockedFetch(async () => {
      await assert.rejects(loadStudySummary(manifestUrl, new AbortController().signal));
    }, url => new Response(url === manifestUrl ? encode(manifest) : bytes));
  }
});

test("unmount cancellation rejects a pending request and a pre-aborted request performs no fetch", async () => {
  await mockedFetch(async calls => {
    const controller = new AbortController(); controller.abort();
    await assert.rejects(loadStudySummary(manifestUrl, controller.signal), { name: "AbortError" });
    assert.equal(calls.length, 0);
  }, () => { throw new Error("Unreachable"); });
  const controller = new AbortController();
  await mockedFetch(async () => {
    const promise = loadStudySummary(manifestUrl, controller.signal);
    controller.abort();
    await assert.rejects(promise, { name: "AbortError" });
  }, (_url, options) => new Promise((_resolve, reject) => {
    options!.signal!.addEventListener("abort", () => reject(options!.signal!.reason), { once: true });
  }));
});

test("leaving the study preserves the caller's abort reason instead of creating an error message", async () => {
  const controller = new AbortController();
  const reason = new DOMException("Synthetic view departure", "AbortError");
  await mockedFetch(async () => {
    const request = loadStudySummary(manifestUrl, controller.signal);
    controller.abort(reason);
    await assert.rejects(request, error => error === reason);
  }, (_url, options) => new Promise((_resolve, reject) => {
    options!.signal!.addEventListener("abort", () => reject(options!.signal!.reason), { once: true });
  }));
});
