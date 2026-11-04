import { memo } from "react";
import { civilianTailDisplay } from "./civilianTail.ts";
import { DecisionInspector } from "./DecisionInspector.tsx";
import { QueueChart } from "./QueueChart.tsx";
import type { Replay } from "./types.ts";

export function metric(value: unknown, suffix = ""): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toLocaleString("en", { maximumFractionDigits: 1 })}${suffix}`
    : "—";
}

/** Outcomes belong to the whole recording, never to the current playback frame. */
export const ReplayEvidence = memo(function ReplayEvidence({
  replay,
  time = 0,
  world = "afterlight",
}: {
  replay: Replay;
  time?: number;
  world?: "afterlight" | "baseline";
}) {
  const worlds = ["afterlight", "baseline"] as const;
  const complete = worlds.every(
    (name) => replay.worlds[name].status === "completed",
  );
  const a = replay.worlds.afterlight.metrics;
  const b = replay.worlds.baseline.metrics;
  const delta =
    typeof a.ambulance_journey_s === "number" &&
    typeof b.ambulance_journey_s === "number"
      ? b.ambulance_journey_s - a.ambulance_journey_s
      : null;
  return (
    <section className="evidence" aria-labelledby="evidence-title">
      <div className="section-heading">
        <span className="eyebrow">This recording</span>
        <h2 id="evidence-title">Measured outcomes</h2>
        <p>Same demand and dispatch. Two independent traffic worlds.</p>
      </div>
      <div className="result-summary">
        <span>Ambulance journey</span>
        <div>
          <strong>{metric(a.ambulance_journey_s, " s")}</strong>
          <small>AFTERLIGHT</small>
        </div>
        <div>
          <strong>{metric(b.ambulance_journey_s, " s")}</strong>
          <small>Ordinary signals</small>
        </div>
        {complete && delta !== null && (
          <p>
            {Math.abs(delta).toFixed(1)} s {delta >= 0 ? "quicker" : "slower"}{" "}
            in this run
          </p>
        )}
      </div>
      <p className="field-note">
        A single run is an example, not an estimate of general performance.
      </p>
      {!complete && (
        <p className="inline-warning" role="status">
          This pair contains incomplete or invalid outcomes. Its travel times do
          not establish a completed-run benefit.
        </p>
      )}
      <div className="evidence-table-wrap">
        <table>
          <caption>Full-run comparison</caption>
          <thead>
            <tr>
              <th scope="col">Measure</th>
              <th scope="col">Afterlight</th>
              <th scope="col">Ordinary</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Run status</th>
              {worlds.map((w) => (
                <td key={w}>{replay.worlds[w].status}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Civilian mean excess time</th>
              {worlds.map((w) => (
                <td key={w}>
                  {metric(
                    replay.worlds[w].metrics.civilian_mean_excess_s,
                    " s",
                  )}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Civilian 95th percentile</th>
              {worlds.map((w) => (
                <td key={w}>{civilianTailDisplay(replay.worlds[w]).value}</td>
              ))}
            </tr>
            {[
              "scheduled",
              "inserted",
              "completed",
              "running",
              "not_inserted",
            ].map((key) => (
              <tr key={key}>
                <th scope="row">
                  {
                    (
                      {
                        scheduled: "Vehicles scheduled",
                        inserted: "Entered network",
                        completed: "Finished journey",
                        running: "Still running",
                        not_inserted: "Did not enter",
                      } as Record<string, string>
                    )[key]
                  }
                </th>
                {worlds.map((w) => (
                  <td key={w}>
                    {metric(
                      (
                        replay.worlds[w].metrics.accounting as
                          | Record<string, unknown>
                          | undefined
                      )?.[key],
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="disclosure">
        <summary>How civilian delay is measured</summary>
        <p>
          Excess time is arrival minus scheduled departure minus each vehicle’s
          saved free-flow reference, floored at zero. It includes waiting to
          enter the network. The 95th percentile uses the nearest rank across
          individual civilians in each world.
        </p>
        {worlds.map((w) => (
          <p key={w}>
            <strong>{w === "afterlight" ? "Afterlight" : "Ordinary"}:</strong>{" "}
            {civilianTailDisplay(replay.worlds[w]).population}
          </p>
        ))}
      </details>
      <QueueChart replay={replay} time={time} world={world} />
      <details className="disclosure">
        <summary>Signal decisions</summary>
        <DecisionInspector replay={replay} />
      </details>
      <details className="disclosure provenance">
        <summary>Source and reproducibility</summary>
        <dl>
          {Object.entries(replay.provenance).map(([key, value]) => (
            <div key={key}>
              <dt>{key.replace(/_/g, " ")}</dt>
              <dd>
                {typeof value === "object"
                  ? JSON.stringify(value)
                  : String(value ?? "—")}
              </dd>
            </div>
          ))}
        </dl>
        <p>
          Playback shows exported simulation states. The viewer does not
          recalculate these outcomes.
        </p>
      </details>
    </section>
  );
});
