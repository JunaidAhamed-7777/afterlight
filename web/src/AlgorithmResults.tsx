import { memo, useMemo } from "react";
import type { Replay } from "./types.ts";
import { algorithmEvidence, type AlgorithmSource } from "./algorithm.ts";
import { seconds } from "./replay.ts";
import "./styles/algorithm.css";

function SourceLinks({ sources }: { sources: AlgorithmSource[] }) {
  return <ul className="algorithm-source-links">{sources.map(item =>
    <li key={item.href}><a href={item.href} target="_blank" rel="noreferrer"
      data-source-file={item.file}>{item.label}</a></li>)}</ul>;
}

export const AlgorithmResults = memo(function AlgorithmResults({ replay }: { replay: Replay | null }) {
  const evidence = useMemo(() => algorithmEvidence(replay), [replay]);
  if (!evidence) return <section className="evidence algorithm-results" aria-labelledby="algorithm-heading">
    <h2 id="algorithm-heading">How this journey works</h2>
    <p className="algorithm-empty">Open a recording from the library to inspect its saved route and how the ambulance and Ordinary-world ghost are displayed.</p>
  </section>;

  return <section className="evidence algorithm-results" aria-labelledby="algorithm-heading"
    data-algorithm={evidence.identifiedImplementation ? "dijkstra-distance" : "unidentified"}>
    <h2 id="algorithm-heading">How this journey works</h2>
    <p className="algorithm-summary">{evidence.identifiedImplementation
      ? "Dijkstra chooses the shortest legal road distance. Signal priority acts on the lamps along that saved route."
      : "This view explains the route metadata and recorded movement. The generating routing implementation is not identified by this file’s source hashes."}</p>
    <p className="algorithm-endpoints"><span>{evidence.networkLabel}</span><br />
      <code>{evidence.pickup}</code><span aria-label="to"> → </span><code>{evidence.hospital}</code></p>

    <dl className="algorithm-worlds" aria-label="Recorded ambulance journeys">
      {evidence.worlds.map(world => <div key={world.id} data-world={world.id}>
        <dt>{world.id === "afterlight" ? "Afterlight ambulance" : <>Ordinary ambulance<small>(ghost when enabled)</small></>}</dt>
        <dd><strong>{seconds(world.journeyS)}</strong><span>{world.status.replace(/_/g, " ")}</span>
          <span className="algorithm-policy">Signals: {world.policy.replace(/_/g, " ")}{world.leadS !== null ? ` · ${world.leadS} s lead` : ""}</span></dd>
      </div>)}
    </dl>
    <p className="algorithm-caption">Whole-recording journey times, separate from the path-search cost.</p>

    <ol className="algorithm-steps">
      <li><h3>Choose legal roads</h3><p>{evidence.identifiedImplementation
        ? "Search the directed road graph through its allowed connections. Minimize the sum of canonical edge lengths in meters, not estimated arrival time."
        : "The file may supply a road-edge sequence, but its search method cannot be established here. Recorded positions alone do not prove a complete route."}</p></li>
      <li><h3>Save the road sequence</h3><p className="algorithm-route-sharing"
        data-route-relation={evidence.sharedRoute ? "shared" : "unverified"}>{evidence.sharedRoute
          ? "Afterlight and Ordinary use the same saved route. It is written into the demand before either simulation starts; neither world searches for a new path."
          : "One scenario route is supplied when available. Separate per-world routes are not exported, so route equality is not asserted for this source."}</p></li>
      <li><h3>Record two journeys</h3><p>Each world has its own traffic, signals and ambulance positions. In a compatible city view, the Ordinary ambulance becomes the cyan ghost when enabled; it does not affect Afterlight traffic.</p>
        {!evidence.worlds[1].hasRecordedAmbulance && <p>No Ordinary ambulance pose is available in this recording.</p>}</li>
      <li><h3>Replay the positions</h3><p>For compatible city recordings, the view draws saved SUMO poses{evidence.sampleStepS !== null ? ` at ${evidence.sampleStepS} s intervals` : " at the exported timestamps"}.
        Positions blend between neighboring samples; no browser pathfinding runs. The road line is a centerline reference, not the lane trajectory. Fixture and other-map recordings keep their evidence without being placed on this city.</p></li>
    </ol>

    {evidence.routeEdges.length > 0 ? <details className="algorithm-route">
      <summary>Exact road sequence · {evidence.routeEdges.length} edges</summary>
      <p>Original <code>scenario.route_edges</code>, in recorded order{evidence.sharedRoute ? ", shared by both ambulances" : ""}.</p>
      <ol className="algorithm-route-edges">{evidence.routeEdges.map((edge, index) =>
        <li key={`${index}:${edge}`} data-edge-id={edge} data-route-index={index}><code>{edge}</code></li>)}</ol>
      {evidence.identifiedImplementation && <>
        <p className="algorithm-cost" data-cost-unit="m">Search cost: <code>Σ canonical edge length_m</code>. The whole starting edge is included. The replay does not supply those edge lengths, so no numeric search total is reconstructed here.</p>
        <dl className="algorithm-lane-distance" aria-label="Recorded external-lane references">
          {evidence.worlds.map(world => <div key={world.id}><dt>{world.id === "afterlight" ? "Afterlight" : "Ordinary"} lane reference</dt>
            <dd data-world={world.id} data-lane-distance-m={world.laneDistanceM ?? undefined}>{world.laneDistanceM === null ? "Unavailable" : `${world.laneDistanceM.toLocaleString("en", { maximumFractionDigits: 1 })} m`}</dd></div>)}
        </dl>
        <p className="algorithm-caption">These separate saved references use SUMO external-lane lengths minus the pickup offset. They exclude internal junction lanes and are not the Dijkstra search total.</p>
      </>}
    </details> : <p className="algorithm-route-empty">No road-edge sequence was exported. Playback still uses the saved positions; an exact route cannot be reconstructed from those poses alone.</p>}

    <details className="algorithm-sources">
      <summary>Source and display details</summary>
      {evidence.identifiedImplementation && <p>Successor edge IDs are sorted. The heap orders <code>(cost, route tuple)</code>; only strictly shorter arrivals update an edge’s stored cost. An equal-cost arrival does not replace the stored route.</p>}
      <p>SUMO records the front bumper. The viewer offsets half the vehicle length to center the model, then maps coordinates to <code>[x, z, −y]</code>. Position interpolation is linear, heading takes the shortest turn, and discontinuities remain jumps. Lifecycle boundaries stay tied to real samples.</p>
      <p>In a compatible city view, the ghost reads the Ordinary frames on the same clock. Its own traffic and lamps can be inspected in Ordinary; it is never inserted into the Afterlight simulation.</p>
      {evidence.offlineSelection && <p>The offline selector chose a saved fixed-lead candidate. It did not choose a different road route.</p>}
      <h3>Recorded simulation source</h3>
      <p>{evidence.captureCommit ? <code>{evidence.captureCommit}</code> : "No usable source revision was exported."}
        {evidence.sourceDirty === true ? " · modified source" : evidence.sourceDirty === false ? " · declared clean" : " · source cleanliness not exported"}</p>
      {!evidence.identifiedImplementation && <p>The reported revision is a reference, not a verified match to the reviewed route generator.</p>}
      <SourceLinks sources={evidence.captureSources} />
      <dl className="algorithm-fingerprints">{evidence.sourceHashes.map(item => <div key={item.file}>
        <dt>{item.file}</dt><dd><code>{item.sha256 ?? "Not exported"}</code></dd></div>)}</dl>
      <p className="algorithm-caption">Identification uses the recording’s exported file hashes. This view does not fetch or independently audit the simulation source.</p>
      <h3>Viewer implementation</h3>
      <SourceLinks sources={evidence.viewerSources} />
    </details>
  </section>;
});
