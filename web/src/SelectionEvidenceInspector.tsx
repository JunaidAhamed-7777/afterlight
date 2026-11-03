import type { SelectionEvidence } from "./types.ts";
import { selectionLabel } from "./selectionEvidence.ts";
export function SelectionEvidenceInspector({ evidence }: { evidence: SelectionEvidence }) {
  return <section className="offline-selection-evidence" aria-label="Offline selector provenance">
    <h3>{selectionLabel(evidence)}</h3>
    <p>This selector chose an already-recorded fixed-lead candidate offline. The recorded traffic,
      signal decisions and timing are unchanged. This is not a live learned controller.</p>
    <p>Case {evidence.case_id} · episode {evidence.episode_id}. A held-out study conclusion is
      not bundled in this view; this one recording does not establish a benefit.</p>
    <details>
      <summary>Selection artifacts and original-world references</summary>
      <p>These are exporter-declared provenance references. The viewer validates their structure
        and consistency, but does not fetch or independently rehash the model, study or original trace files.</p>
      <dl>
        {Object.entries(evidence).filter(([key]) => key.endsWith("_sha256")).map(([key, value]) =>
          <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd>{value == null ? "No model (analytical selector)" : String(value)}</dd></div>)}
        {(["afterlight", "baseline"] as const).map(alias => {
          const source = evidence.source_world_aliases[alias];
          return <div key={alias}><dt>{alias} source world</dt>
            <dd>{source.original_world_id}<br />{source.trace_file}<br />{source.trace_sha256}</dd></div>;
        })}
      </dl>
      <p>Exporter interpretation: {evidence.interpretation}</p>
    </details>
  </section>;
}
