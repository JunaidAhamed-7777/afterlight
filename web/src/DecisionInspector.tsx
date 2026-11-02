import { memo } from "react";
import type { Replay } from "./types.ts";
export const DecisionInspector = memo(function DecisionInspector({
  replay,
}: {
  replay: Replay;
}) {
  const world = replay.worlds.afterlight;
  const dispatch = world.events.find((e) => e.kind === "dispatch");
  const transitions = world.events
    .filter((e) =>
      ["request_planned", "request", "priority_green", "release"].includes(
        String(e.kind),
      ),
    )
    .sort((a, b) => Number(a.t) - Number(b.t));
  return (
    <details className="provenance decision-inspector">
      <summary>Dispatch decision & legal priority sequence</summary>
      {dispatch ? (
        <>
          <p>
            The {world.policy} decision was frozen at{" "}
            {Number(dispatch.t).toFixed(1)} s.{" "}
            {dispatch.selected_lead_s == null
              ? "No fixed clearance lead applies."
              : `Selected clearance lead: ${dispatch.selected_lead_s} s.`}{" "}
            Requests are not instantaneous green lights.
          </p>
          <dl>
            <div>
              <dt>Effective schedules</dt>
              <dd>
                {String(dispatch.effective_candidate_count ?? "Not recorded")}
              </dd>
            </div>
            <div>
              <dt>Frozen request plan</dt>
              <dd>{JSON.stringify(dispatch.request_plan ?? {})}</dd>
            </div>
            <div>
              <dt>Observed inputs</dt>
              <dd>{JSON.stringify(dispatch.observation ?? {})}</dd>
            </div>
            <div>
              <dt>Analytical prediction</dt>
              <dd>{JSON.stringify(dispatch.candidate_prediction ?? {})}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p>No dispatch decision event was recorded.</p>
      )}
      {transitions.length > 0 && (
        <div className="decision-table">
          <table>
            <caption>
              Full recorded priority sequence, including events after the
              playback cursor
            </caption>
            <thead>
              <tr>
                <th>Time (s)</th>
                <th>Junction</th>
                <th>Event</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {transitions.map((e, i) => (
                <tr key={i}>
                  <td>{Number(e.t).toFixed(1)}</td>
                  <td>{String(e.junction ?? "—")}</td>
                  <td>{String(e.kind).replace(/_/g, " ")}</td>
                  <td>
                    {e.request_at_s !== undefined
                      ? `Request planned for ${e.request_at_s} s`
                      : String(
                          e.reason ??
                            (e.phase !== undefined ? `Phase ${e.phase}` : "—"),
                        )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
});
