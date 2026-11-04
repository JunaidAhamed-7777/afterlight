import { useEffect, useRef, useState } from "react";
import { readSimulationResponse, type SimulationEvent } from "./cloudSimulation.ts";
import { loadRecording } from "./recording.ts";
import type { Replay } from "./types.ts";

interface Status {
  busy: boolean;
  phase: string;
  progress: number | null;
  error: string;
  routeEdges: string[];
  routeMapHash: string;
}
const idle: Status = { busy: false, phase: "", progress: null, error: "", routeEdges: [], routeMapHash: "" };
export function useCloudSimulation(endpoint: string, onReady: (replay: Replay, url: string) => void) {
  const [status, setStatus] = useState<Status>(idle);
  const operation = useRef<AbortController | null>(null);
  const ready = useRef(onReady);
  const urls = useRef(new Set<string>());
  ready.current = onReady;
  useEffect(() => () => {
    operation.current?.abort();
    for (const url of urls.current) URL.revokeObjectURL(url);
  }, []);
  async function start(pickup: string, hospital: string) {
    if (operation.current) return;
    const controller = new AbortController();
    operation.current = controller;
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(295000)]);
    const requestId = crypto.randomUUID().replaceAll("-", "");
    let artifactUrl = "";
    setStatus({ ...idle, busy: true, phase: "Connecting to the simulation server" });
    const update = (event: SimulationEvent) => {
      if (operation.current !== controller || signal.aborted) return;
      if (event.type === "route") {
        if (event.pickup !== pickup || event.hospital !== hospital || !Array.isArray(event.route_edges) ||
          !event.route_edges.length || event.route_edges.length > 512 ||
          !event.route_edges.every(edge => typeof edge === "string" && edge.length <= 160) ||
          typeof event.canonical_map_sha256 !== "string") throw new Error("The calculated route does not match this journey.");
        setStatus(previous => ({ ...previous, routeEdges: event.route_edges as string[], routeMapHash: event.canonical_map_sha256 as string }));
        return;
      }
      if (event.type !== "progress") return;
      const phase = typeof event.phase === "string" ? event.phase : "preparing";
      const worldName = event.world_id === "baseline" ? "ordinary" : "priority";
      const label = phase === "simulating" ? `Calculating ${worldName} traffic` :
        phase === "pathfinding" ? "Finding the ambulance route" :
        phase === "building_network" ? "Preparing city roads" :
        phase === "starting_world" ? `Starting ${worldName} traffic` :
        ["compressing", "ready", "validating_export", "validating_replay", "reconciling_world"].includes(phase)
          ? "Checking the simulation and preparing playback" : "Preparing the simulation";
      const completed = event.completed_steps, total = event.total_steps;
      let fraction: number | null = null;
      if (typeof completed === "number" && Number.isSafeInteger(completed) && completed >= 0 &&
        typeof total === "number" && Number.isSafeInteger(total) && total > 0 && completed <= total)
        fraction = ((event.world_id === "afterlight" ? 1 : 0) + completed / total) / 2;
      setStatus(previous => ({ ...previous, phase: label, progress: fraction ?? previous.progress }));
    };
    try {
      const response = await fetch(endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId, pickup, hospital }), signal,
      });
      const artifact = await readSimulationResponse(response, requestId, signal, update);
      artifactUrl = artifact.url;
      setStatus(previous => ({ ...previous, phase: "Opening the calculated traffic", progress: 1 }));
      const replay = await loadRecording(null, artifact.url, signal, artifact.replaySha256);
      if (signal.aborted || operation.current !== controller) return;
      if (replay.scenario.id !== artifact.scenarioId || replay.scenario.network_kind !== "city" ||
        replay.scenario.pickup_id !== pickup || replay.scenario.hospital_id !== hospital ||
        replay.scenario.split !== "pilot" || replay.duration_s !== 900 || replay.step_s !== .5)
        throw new Error("The calculated recording does not match your selected journey.");
      urls.current.add(artifact.url);
      ready.current(replay, artifact.url);
      artifactUrl = "";
      setStatus({ ...idle, phase: "Simulation ready" });
    } catch (error) {
      if (operation.current === controller) setStatus({ ...idle,
        phase: controller.signal.aborted ? "Simulation canceled" : "",
        error: controller.signal.aborted ? "" : signal.aborted
          ? "The simulation took too long. Try again or choose another journey."
          : error instanceof Error ? error.message : "The simulation could not finish. Try again.",
      });
    } finally {
      if (artifactUrl) URL.revokeObjectURL(artifactUrl);
      if (operation.current === controller) operation.current = null;
    }
  }
  return { ...status, start, cancel: () => operation.current?.abort() };
}
