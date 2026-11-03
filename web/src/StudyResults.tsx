import { useEffect, useId, useState } from "react";
import {
  loadStudySummary,
  studyArtifactUrl,
  StudyUnpublishedError,
  type LoadedStudy,
  type StudyComparison,
} from "./studySummary.ts";
import "./styles/study.css";

type State =
  | { status: "loading" }
  | { status: "ready"; study: LoadedStudy }
  | { status: "unpublished" }
  | { status: "error"; message: string };

function signed(value: number | null): string {
  if (value === null) return "Unavailable";
  const magnitude = Math.abs(value);
  const formatted = magnitude !== 0 && (magnitude < .1 || magnitude >= 1e6)
    ? magnitude.toPrecision(2) : magnitude.toFixed(1);
  return `${value < 0 ? "−" : value > 0 ? "+" : ""}${formatted} s`;
}
const integer = (value: number) => value.toLocaleString("en");

function Comparison({ comparison }: { comparison: StudyComparison }) {
  const titleId = useId();
  const row = comparison;
  return (
    <section className="study-comparison" aria-labelledby={titleId}>
      <h3 id={titleId}>{row.selected_label} <span>vs</span> {row.comparator_label}</h3>
      <p className="study-population">
        All {integer(row.episodes)} test episodes · {integer(row.demand_groups)} demand groups
      </p>
      <dl className="study-failures">
        <div><dt>{row.selected_label} failures</dt><dd>{integer(row.selected_failures)} / {integer(row.episodes)}</dd></div>
        <div><dt>{row.comparator_label} failures</dt><dd>{integer(row.comparator_failures)} / {integer(row.episodes)}</dd></div>
      </dl>
      <p className="study-condition">
        Finite comparisons below use {integer(row.paired_feasible_episodes)} of {integer(row.episodes)} pairs
        with valid, complete objectives in both choices. Unavailable objectives remain in the counts above.
      </p>
      <dl className="study-deltas">
        <div className="study-objective"><dt>Mean objective delta</dt><dd>{signed(row.mean_delta_j_s)}</dd></div>
        <div><dt>Ambulance delta</dt><dd>{signed(row.mean_delta_ambulance_s)}</dd></div>
        <div><dt>Civilian mean excess delta</dt><dd>{signed(row.mean_delta_civilian_s)}</dd></div>
      </dl>
      <p className="study-interval">
        <strong>Objective 95% interval:</strong>{" "}
        {row.interval_95_j_s
          ? `${signed(row.interval_95_j_s[0])} to ${signed(row.interval_95_j_s[1])}`
          : `Unavailable — ${row.interval_reason}`}
        <span>Independent demand groups for the interval: {integer(row.interval_groups)}.</span>
      </p>
      <p className="study-action-rate">
        Different candidate choice: {(row.changed_action_rate * 100).toLocaleString("en", { maximumFractionDigits: 1 })}% of test episodes.
      </p>
      <details className="disclosure study-statuses">
        <summary>All world status counts</summary>
        <p>Failures mean unavailable objectives. A completed world can still have an unavailable objective.</p>
        <div className="study-table-wrap">
          <table className="study-accounting">
            <caption>All {integer(row.episodes)} test episodes in each choice</caption>
            <thead>
              <tr><th scope="col">World status</th><th scope="col">{row.selected_label}</th><th scope="col">{row.comparator_label}</th></tr>
            </thead>
            <tbody>
              {(["completed", "censored", "invalid", "infrastructure_error"] as const).map(status => (
                <tr key={status}>
                  <th scope="row">{status === "infrastructure_error" ? "Infrastructure errors" : status[0].toUpperCase() + status.slice(1)}</th>
                  <td>{integer(row.selected_status_counts[status])}</td><td>{integer(row.comparator_status_counts[status])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

/** Render only in the active Study subview: no publication request occurs before mounting. */
export function StudyResults() {
  const titleId = useId();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    const url = new URL(`${import.meta.env.BASE_URL}study/manifest.json`, location.href).href;
    loadStudySummary(url, controller.signal).then(
      study => { if (!controller.signal.aborted) setState({ status: "ready", study }); },
      error => {
        if (controller.signal.aborted) return;
        setState(error instanceof StudyUnpublishedError
          ? { status: "unpublished" }
          : { status: "error", message: error instanceof Error ? error.message : "The study evidence could not load." });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  if (state.status !== "ready") {
    return (
      <section className="evidence study-results study-empty" aria-labelledby={titleId} aria-busy={state.status === "loading"}>
        <div className="section-heading">
          <span className="eyebrow">Held-out study</span>
          <h2 id={titleId}>{state.status === "loading" ? "Loading study evidence…" : state.status === "unpublished" ? "Study not published" : "Study evidence unavailable"}</h2>
        </div>
        <p role="status">
          {state.status === "loading" ? "Checking the published summary and its checksum."
            : state.status === "unpublished" ? "This build has no audited study summary. Open This run to inspect an individual recording."
              : state.message}
        </p>
        {state.status !== "loading" && <button className="text-button" onClick={() => setAttempt(value => value + 1)}>Retry study</button>}
      </section>
    );
  }
  const { summary, manifest, manifestUrl, summaryUrl } = state.study;
  return (
    <section className="evidence study-results" aria-labelledby={titleId}>
      <div className="section-heading">
        <span className="eyebrow">Held-out study</span>
        <h2 id={titleId}>{summary.mode === "learned" ? "Offline selector results" : "Analytical baseline results"}</h2>
        <p>Frozen test evidence. Each comparison keeps every test episode in its accounting.</p>
      </div>
      {summary.mode === "baseline_only" && <p className="study-mode-note">This release compares the analytical planner with tuned fixed lead. It contains no learned-model result.</p>}
      <dl className="study-counts">
        <div><dt>Test episodes</dt><dd>{integer(summary.counts.test)}</dd></div>
        <div><dt>Demand groups</dt><dd>{integer(summary.counts.test_demand_groups)}</dd></div>
        <div><dt>Test worlds</dt><dd>{integer(summary.counts.test_worlds)}</dd></div>
      </dl>
      <p className="study-sign-rule">Deltas are selected choice minus comparator, in seconds. Negative is lower; positive is higher. A faster ambulance can still increase civilian cost.</p>
      {summary.comparisons.map(comparison => <Comparison key={comparison.id} comparison={comparison} />)}
      <details className="disclosure study-method">
        <summary>Study design and objective</summary>
        <dl>
          <div><dt>Train / validation / test episodes</dt><dd>{integer(summary.counts.train)} / {integer(summary.counts.validation)} / {integer(summary.counts.test)}</dd></div>
          <div><dt>Held-out demand regimes</dt><dd>{summary.holdouts.regimes.join(", ") || "No additional regime holdout"}</dd></div>
          <div><dt>Held-out route families</dt><dd>{summary.holdouts.route_families.join(", ") || "No additional route-family holdout"}</dd></div>
          <div><dt>Tuned fixed lead</dt><dd>{summary.fixed_lead_s} s</dd></div>
          <div><dt>Objective, civilian weight 1</dt><dd>{summary.objective.definition}</dd></div>
        </dl>
        <p>The selector chooses among cached, previously simulated candidate worlds. These results describe offline candidate selection, not live learned traffic control.</p>
        <p>Failure counts mean that an objective was unavailable. A completed world can still lack a usable objective. Confidence intervals use independent demand groups; missing intervals retain the report’s reason.</p>
      </details>
      <details className="disclosure provenance study-provenance">
        <summary>Source and download artifacts</summary>
        <p>The summary’s {integer(manifest.bytes)} bytes match its published SHA-256. Artifact links and hashes below are published provenance; opening this panel does not download or independently audit every artifact.</p>
        <ul className="study-downloads">
          <li><a href={`https://github.com/JunaidAhamed-7777/afterlight/tree/${summary.provenance.source_commit}`} target="_blank" rel="noreferrer">Scientific source commit</a></li>
          <li><a href={manifestUrl} download>Publication manifest</a></li>
          <li><a href={summaryUrl} download>Verified study summary</a></li>
          {summary.artifacts.map(artifact => (
            <li key={artifact.url}>
              <a href={studyArtifactUrl(artifact.url, summaryUrl)} download>{artifact.kind.replace(/_/g, " ")}</a>
              <span>{integer(artifact.bytes)} bytes</span><code>{artifact.sha256}</code>
            </li>
          ))}
        </ul>
        <dl>
          <div><dt>Summary SHA-256</dt><dd>{manifest.sha256}</dd></div>
          {Object.entries(summary.provenance).map(([key, value]) => <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd>{value ?? "No learned model in this release"}</dd></div>)}
        </dl>
      </details>
    </section>
  );
}
