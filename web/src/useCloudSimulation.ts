import { useEffect, useRef, useState } from "react";
import { readSimulationResponse, type SimulationEvent } from "./cloudSimulation.ts";
import { loadRecording } from "./recording.ts";
import type { Replay } from "./types.ts";
import type { QueueSeries } from "./queueTypes.ts";
import { boundedBytes } from "./response.ts";
import { parseJsonBytes } from "./strictJson.ts";

interface Status {
  busy: boolean;
  phase: string;
  progress: number | null;
  error: string;
  routeEdges: string[];
  routeMapHash: string;
  queues: QueueSeries;
  activeWorld: "afterlight" | "baseline";
  canceling: boolean;
  cancelError: string;
}
const idle: Status = { busy: false, phase: "", progress: null, error: "", routeEdges: [], routeMapHash: "",
  queues: { afterlight: [], baseline: [] }, activeWorld: "baseline", canceling: false, cancelError: "" };
export function useCloudSimulation(endpoint: string, onReady: (replay: Replay, url: string) => void) {
  const [status, setStatus] = useState<Status>(idle);
  const operation = useRef<AbortController | null>(null);
  const ready = useRef(onReady);
  const urls = useRef(new Set<string>());
  const queueBuffers = useRef<QueueSeries>({ afterlight: [], baseline: [] });
  const queueTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const request = useRef<string | null>(null);
  const cancelRequested = useRef(false);
  const cancelInFlight = useRef(false);
  const serverFinished = useRef(false);
  const serverAccepted = useRef(false);
  const cancelUrl = () => new URL("./cancel", new URL(endpoint, location.href)).href;
  ready.current = onReady;
  useEffect(() => () => {
    const active = operation.current;
    operation.current = null;
    if (active && request.current && !serverFinished.current) {
      navigator.sendBeacon?.(cancelUrl(), new Blob([JSON.stringify({ request_id: request.current })], { type: "application/json" }));
    }
    active?.abort();
    if (queueTimer.current !== null) clearTimeout(queueTimer.current);
    for (const url of urls.current) URL.revokeObjectURL(url);
  }, []);
  async function start(pickup: string, hospital: string) {
    if (operation.current) return;
    const controller = new AbortController();
    operation.current = controller;
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(295000)]);
    const requestId = crypto.randomUUID().replaceAll("-", "");
    request.current = requestId;
    cancelRequested.current = false;
    cancelInFlight.current = false;
    serverFinished.current = false;
    serverAccepted.current = false;
    let artifactUrl = "";
    queueBuffers.current = { afterlight: [], baseline: [] };
    if (queueTimer.current !== null) clearTimeout(queueTimer.current);
    queueTimer.current = null;
    setStatus({ ...idle, busy: true, phase: "Connecting to the simulation server" });
    const update = (event: SimulationEvent) => {
      if (operation.current !== controller || signal.aborted) return;
      if (event.type === "accepted") { serverAccepted.current = true; return; }
      if (event.type === "queue") {
        const { world_id: world, t, queue_count: count } = event;
        if ((world !== "baseline" && world !== "afterlight") ||
          typeof t !== "number" || !Number.isFinite(t) || t < 0 || t > 900 ||
          typeof count !== "number" || !Number.isSafeInteger(count) || count < 0)
          throw new Error("The simulation returned an invalid queue sample.");
        const samples = queueBuffers.current[world];
        if (samples.length >= 4096 || (samples.length && t <= samples[samples.length - 1].t))
          throw new Error("The simulation queue timeline is invalid.");
        samples.push({ t, queue_count: count });
        if (queueTimer.current === null) queueTimer.current = setTimeout(() => {
          queueTimer.current = null;
          if (operation.current !== controller || signal.aborted) return;
          setStatus(previous => ({ ...previous, activeWorld: world,
            queues: { afterlight: queueBuffers.current.afterlight.slice(), baseline: queueBuffers.current.baseline.slice() },
          }));
        }, 250);
        return;
      }
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
      setStatus(previous => ({ ...previous, phase: previous.canceling ? previous.phase : label, progress: fraction ?? previous.progress,
        activeWorld: event.world_id === "baseline" || event.world_id === "afterlight" ? event.world_id : previous.activeWorld,
      }));
    };
    try {
      const response = await fetch(endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId, pickup, hospital }), signal,
      });
      const artifact = await readSimulationResponse(response, requestId, signal, update);
      artifactUrl = artifact.url;
      serverFinished.current = true;
      if (cancelRequested.current) { controller.abort(); signal.throwIfAborted(); }
      setStatus(previous => ({ ...previous, phase: "Opening the calculated traffic", progress: 1 }));
      const replay = await loadRecording({
        id: artifact.scenarioId, title: "Calculated journey", url: artifact.url,
        sha256: artifact.replaySha256, bytes: artifact.decodedBytes,
        pickup_id: pickup, hospital_id: hospital, seed: 7,
        policy: "fixed", lead_s: 20, duration_s: 900,
      }, artifact.url, signal);
      if (signal.aborted || operation.current !== controller) return;
      if (replay.scenario.id !== artifact.scenarioId || replay.scenario.network_kind !== "city" ||
        replay.scenario.pickup_id !== pickup || replay.scenario.hospital_id !== hospital ||
        replay.scenario.split !== "pilot" || replay.duration_s !== 900 || replay.step_s !== .5)
        throw new Error("The calculated recording does not match your selected journey.");
      for (const previous of urls.current) URL.revokeObjectURL(previous);
      urls.current.clear();
      urls.current.add(artifact.url);
      ready.current(replay, artifact.url);
      artifactUrl = "";
      setStatus(previous => ({ ...previous, busy: false, phase: "Simulation ready", progress: 1,
        queues: { afterlight: queueBuffers.current.afterlight.slice(), baseline: queueBuffers.current.baseline.slice() },
      }));
    } catch (error) {
      if (serverAccepted.current && !serverFinished.current &&
        !(error instanceof DOMException && error.name === "AbortError" && cancelRequested.current)) {
        navigator.sendBeacon?.(cancelUrl(), new Blob([JSON.stringify({ request_id: requestId })], { type: "application/json" }));
      }
      if (operation.current === controller) setStatus(previous => ({ ...previous, busy: false,
        canceling: false, cancelError: "",
        queues: { afterlight: queueBuffers.current.afterlight.slice(), baseline: queueBuffers.current.baseline.slice() },
        phase: controller.signal.aborted || (cancelRequested.current && error instanceof DOMException && error.name === "AbortError") ? "Simulation canceled" : "",
        error: controller.signal.aborted || (cancelRequested.current && error instanceof DOMException && error.name === "AbortError") ? "" : signal.aborted
          ? "The simulation took too long. Try again or choose another journey."
          : error instanceof Error ? error.message : "The simulation could not finish. Try again.",
      }));
    } finally {
      if (artifactUrl) URL.revokeObjectURL(artifactUrl);
      if (queueTimer.current !== null) clearTimeout(queueTimer.current);
      queueTimer.current = null;
      if (operation.current === controller) operation.current = null;
    }
  }
  async function cancel() {
    const active = operation.current, requestId = request.current;
    if (!active || !requestId || cancelInFlight.current) return;
    cancelRequested.current = true;
    if (serverFinished.current) { active.abort(); return; }
    cancelInFlight.current = true;
    setStatus(previous => ({ ...previous, canceling: true, cancelError: "", phase: "Stopping the simulation" }));
    try {
      const response = await fetch(cancelUrl(), { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId }), signal: AbortSignal.timeout(10000),
      });
      const result = parseJsonBytes(await boundedBytes(response, 4096)) as { request_id?: unknown; cancel_requested?: unknown };
      if (!response.ok || result.request_id !== requestId || result.cancel_requested !== true)
        throw new Error("Cancellation was not confirmed.");
      // Keep reading until the server confirms its owned processes are stopped.
    } catch {
      if (operation.current === active && !active.signal.aborted) {
        setStatus(previous => ({ ...previous, canceling: false,
          phase: "Calculating the simulation", cancelError: "Could not confirm cancellation. Try Cancel again.",
        }));
      }
    } finally { cancelInFlight.current = false; }
  }
  return { ...status, start, cancel,
    clear: () => { if (!operation.current) setStatus(idle); },
  };
}
