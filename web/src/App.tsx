import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
const CityView = lazy(() =>
  import("./CityView.tsx").then((module) => ({ default: module.CityView })),
);
import { bindRecording, loadRecording } from "./recording.ts";
import { LocalGeneration } from "./LocalGeneration.tsx";
import { CanvasBoundary } from "./CanvasBoundary.tsx";
import { loadCanonicalCity, geometryMatches } from "./city.ts";
import { DecisionInspector } from "./DecisionInspector.tsx";
import { QueueChart } from "./QueueChart.tsx";
import { recordingUrl, validateCatalog } from "./catalog.ts";
import { frameAt, seconds, validateReplay } from "./replay.ts";
import type { CatalogEntry, City, Replay } from "./types.ts";
const base = import.meta.env.BASE_URL;
const apiBase = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(
  /\/$/,
  "",
);
const source = apiBase
  ? `${apiBase}/api/catalog`
  : `${base}replays/catalog.json`;
const catalogBase = apiBase
  ? `${apiBase}/`
  : new URL(`${base}replays/`, location.href).href;
async function json(url: string, signal: AbortSignal) {
  const timeout = AbortSignal.timeout(30000);
  const r = await fetch(url, { signal: AbortSignal.any([signal, timeout]) });
  if (!r.ok)
    throw new Error(
      `Request failed (${r.status}). Check the recording files and retry.`,
    );
  return r.json();
}
function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const m = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(m.matches);
    m.addEventListener("change", update);
    return () => m.removeEventListener("change", update);
  }, []);
  return reduced;
}
function Icon({
  name,
}: {
  name: "play" | "pause" | "reset" | "arrow" | "expand";
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {name === "play" ? (
        <path d="m9 5 10 7-10 7Z" />
      ) : name === "pause" ? (
        <>
          <path d="M8 5v14M16 5v14" />
        </>
      ) : name === "reset" ? (
        <>
          <path d="M4 10a8 8 0 1 1 1 8M4 4v6h6" />
        </>
      ) : name === "expand" ? (
        <>
          <path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" />
        </>
      ) : (
        <path d="M4 12h16m-6-6 6 6-6 6" />
      )}
    </svg>
  );
}
export default function App() {
  const [cityHash, setCityHash] = useState("");
  const [cityError, setCityError] = useState(""),
    [cityRetry, setCityRetry] = useState(0);
  const [city, setCity] = useState<City | null>(null),
    [catalog, setCatalog] = useState<CatalogEntry[]>([]),
    [catalogStatus, setCatalogStatus] = useState(
      "Loading available recordings…",
    ),
    [catalogError, setCatalogError] = useState(false),
    [catalogRetry, setCatalogRetry] = useState(0);
  const [pickup, setPickup] = useState("P001"),
    [hospital, setHospital] = useState("HOSP_WEST"),
    [search, setSearch] = useState(""),
    [selection, setSelection] = useState("");
  const [replay, setReplay] = useState<Replay | null>(null),
    [loading, setLoading] = useState(false),
    [loadError, setLoadError] = useState(""),
    [loadRetry, setLoadRetry] = useState(0),
    [time, setTime] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1);
  const [world, setWorld] = useState<"afterlight" | "baseline">("afterlight"),
    [ghost, setGhost] = useState(true),
    [ghostOpacity, setGhostOpacity] = useState(0.38),
    [quality, setQuality] = useState<"balanced" | "high">("balanced"),
    [follow, setFollow] = useState(false),
    [reset, setReset] = useState(0),
    [motionOff, setMotionOff] = useState(false);
  const [generating, setGenerating] = useState(false);
  const generatedReplays = useRef(new Map<string, Replay>());
  const playbackClock = useRef(0);
  const seekTime = (t: number) => {
    playbackClock.current = t;
    setTime(t);
  };
  const prefersReduced = useReducedMotion(),
    reducedMotion = prefersReduced || motionOff;
  useEffect(() => {
    const c = new AbortController();
    setCityError("");
    loadCanonicalCity(`${base}assets/map/city_manifest.json`, c.signal)
      .then(({ city, sha256 }) => {
        if (!c.signal.aborted) {
          setCity(city);
          setCityHash(sha256);
        }
      })
      .catch((error) => {
        if (!c.signal.aborted)
          setCityError(
            `The canonical city map could not load: ${error instanceof Error ? error.message : "unknown format"} Retry to restore pickup selection.`,
          );
      });
    return () => c.abort();
  }, [cityRetry]);
  useEffect(() => {
    const c = new AbortController();
    setCatalogError(false);
    setCatalogStatus("Loading available recordings…");
    json(source, c.signal)
      .then((d) => {
        if (c.signal.aborted) return;
        const runs = validateCatalog(d, catalogBase);
        setCatalog(runs);
        setCatalogStatus(
          runs.length ? "" : "No recorded experiments published yet.",
        );
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setCatalogError(true);
          setCatalogStatus(e.message);
        }
      });
    return () => c.abort();
  }, [catalogRetry]);
  useEffect(() => {
    setReplay(null);
    setPlaying(false);
    seekTime(0);
    setLoadError("");
    if (!selection) {
      setLoading(false);
      return;
    }
    const item = catalog.find((x) => x.id === selection);
    if (!item) return;
    const c = new AbortController();
    setLoading(true);
    const url = recordingUrl(item.url, catalogBase);
    (generatedReplays.current.has(selection)
      ? Promise.resolve().then(() =>
          bindRecording(
            validateReplay(generatedReplays.current.get(selection)),
            item,
          ),
        )
      : loadRecording(item, url, c.signal)
    )
      .then((r) => {
        if (!c.signal.aborted) {
          setReplay(r);
          setPickup(r.scenario.pickup_id);
          setHospital(r.scenario.hospital_id);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setLoadError(e.message);
          setLoading(false);
        }
      });
    return () => c.abort();
  }, [selection, catalog, loadRetry]);
  useEffect(() => {
    if (!playing || !replay) return;
    let raf = 0,
      last = performance.now(),
      lastPublished = last;
    const tick = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.1) * speed;
      last = now;
      playbackClock.current = Math.min(
        playbackClock.current + dt,
        replay.duration_s,
      );
      if (
        now - lastPublished >= 100 ||
        playbackClock.current >= replay.duration_s
      ) {
        setTime(playbackClock.current);
        lastPublished = now;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, replay, speed]);
  useEffect(() => {
    if (replay && time >= replay.duration_s && playing) setPlaying(false);
  }, [time, replay, playing]);
  useEffect(() => {
    if (reducedMotion) setFollow(false);
  }, [reducedMotion]);
  const cityReplay = Boolean(
    replay &&
      replay.scenario.network_kind === "city" &&
      geometryMatches(replay.provenance.canonical_map_sha256, cityHash),
  );
  const available = catalog.filter(
    (x) => x.pickup_id === pickup && x.hospital_id === hospital,
  );
  const pickups = useMemo(
    () =>
      city?.pickups.filter((x) =>
        `${x.id} ${x.road_id}`.toLowerCase().includes(search.toLowerCase()),
      ) ?? [],
    [city, search],
  );
  const changeRoute = (p: string, h: string) => {
    setPickup(p);
    setHospital(h);
    setSelection("");
    setReplay(null);
    setPlaying(false);
    seekTime(0);
  };
  const selectRecording = (id: string) => {
    setSelection(id);
    setReplay(null);
    setPlaying(false);
    seekTime(0);
    setLoadError("");
    setLoading(Boolean(id));
  };
  const activeHospital = city?.hospitals.find((x) => x.id === hospital);
  const timelineMax = replay?.duration_s ?? 1;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#experiment-controls">
        Skip to experiment controls
      </a>
      <header className="topbar">
        <a className="wordmark" href={base} aria-label="AFTERLIGHT home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          AFTERLIGHT<span className="wordmark-stop">.</span>
        </a>
        <p>Clear the path. Understand the aftermath.</p>
        <a
          className="source-link"
          href="https://github.com/JunaidAhamed-7777/afterlight"
          target="_blank"
          rel="noreferrer"
        >
          Source & method <Icon name="arrow" />
        </a>
      </header>
      <main>
        <section className="workspace" aria-label="Traffic experiment">
          <aside className="control-panel" id="experiment-controls">
            <div className="intro">
              <h1>
                One city.
                <br />
                <span>Two futures.</span>
              </h1>
              <p>
                Compare ambulance clearance with the traffic it leaves behind.
              </p>
            </div>
            <div className="mode-label">
              <span className={replay ? "status-dot recorded" : "status-dot"} />
              {replay
                ? "Recorded simulation"
                : generating
                  ? "Local generation in progress"
                  : apiBase
                    ? "Local experiment library"
                    : "City exploration"}
            </div>
            {cityError && (
              <div className="map-error" role="alert">
                <p>{cityError}</p>
                <button onClick={() => setCityRetry((x) => x + 1)}>
                  Retry city map
                </button>
              </div>
            )}
            <div className="route-control">
              <h2>Choose a journey</h2>
              <label htmlFor="pickup-search">Find a pickup</label>
              <input
                id="pickup-search"
                type="search"
                placeholder="Pickup ID or road"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoComplete="off"
              />
              <label htmlFor="pickup">Pickup point</label>
              <select
                id="pickup"
                value={pickup}
                onChange={(e) => changeRoute(e.target.value, hospital)}
                disabled={!city}
              >
                {!pickups.some((x) => x.id === pickup) && (
                  <option value={pickup}>{pickup} · selected</option>
                )}
                {pickups.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.id} · {p.road_id}
                  </option>
                ))}
              </select>
              <span className="field-note">
                {city
                  ? `${pickups.length} of ${city.pickups.length} canonical curb anchors`
                  : "Loading canonical map…"}
              </span>
              <label htmlFor="hospital">Destination hospital</label>
              <select
                id="hospital"
                value={hospital}
                onChange={(e) => changeRoute(pickup, e.target.value)}
                disabled={!city}
              >
                {city && !city.hospitals.some((h) => h.id === hospital) && (
                  <option value={hospital}>
                    {hospital} · recorded destination
                  </option>
                )}
                {city?.hospitals.map((h) => (
                  <option value={h.id} key={h.id}>
                    {h.name ?? h.id}
                  </option>
                ))}
              </select>
              <div className="journey-line">
                <span className="route-origin" />
                <span>{pickup}</span>
                <span className="route-rule" />
                <Icon name="arrow" />
                <span>
                  {hospital === "HOSP_WEST"
                    ? "Westhaven"
                    : hospital === "HOSP_EAST"
                      ? "Eastbank"
                      : "Fixture endpoint"}
                </span>
                <span className="route-destination" />
              </div>
            </div>
            <div className="recording-control">
              <label htmlFor="recording">Recorded experiment</label>
              <select
                id="recording"
                value={selection}
                onChange={(e) => selectRecording(e.target.value)}
                disabled={!available.length || loading}
              >
                <option value="">
                  {available.length
                    ? "Select a paired run"
                    : "No recording for this journey"}
                </option>
                {available.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title} · seed {r.seed}
                  </option>
                ))}
              </select>
              {catalogStatus && (
                <p className="field-note" role="status">
                  {catalogStatus}
                </p>
              )}
              {catalogError && (
                <button onClick={() => setCatalogRetry((x) => x + 1)}>
                  Retry catalog
                </button>
              )}
              {!selection && (
                <p className="recording-help">
                  Explore the original map now. Traffic and results appear only
                  when a genuine paired SUMO recording is available.
                </p>
              )}
              {catalog.length > 0 && (
                <details>
                  <summary>All available recordings ({catalog.length})</summary>
                  <ul className="recording-list">
                    {catalog.map((r) => (
                      <li key={r.id}>
                        <button
                          onClick={() => {
                            setPickup(r.pickup_id);
                            setHospital(r.hospital_id);
                            selectRecording(r.id);
                          }}
                        >
                          {r.title}
                          <small>
                            {r.pickup_id} → {r.hospital_id} · seed {r.seed} · {r.policy_label ?? r.policy}
                          </small>
                        </button>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
            {apiBase && (
              <LocalGeneration
                apiBase={apiBase}
                pickup={pickup}
                hospital={hospital}
                mapReady={Boolean(city)}
                onBusy={setGenerating}
                onStarted={() => {
                  setSelection("");
                  setReplay(null);
                  setPlaying(false);
                  seekTime(0);
                }}
                onOpen={(r, url) => {
                  generatedReplays.current.set(r.scenario.id, r);
                  const entry: CatalogEntry = {
                    id: r.scenario.id,
                    title: `Local ${r.worlds.afterlight.policy} run`,
                    url,
                    seed: r.scenario.seed,
                    pickup_id: r.scenario.pickup_id,
                    hospital_id: r.scenario.hospital_id,
                    policy: r.worlds.afterlight.policy,
                    lead_s: r.worlds.afterlight.lead_s,
                    duration_s: r.duration_s,
                  };
                  setCatalog((rows) => [
                    ...rows.filter((row) => row.id !== entry.id),
                    entry,
                  ]);
                  selectRecording(entry.id);
                  setPickup(entry.pickup_id);
                  setHospital(entry.hospital_id);
                }}
              />
            )}
            <div className="view-options">
              <h2>View settings</h2>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={ghost}
                  disabled={!cityReplay || world === "baseline"}
                  onChange={(e) => setGhost(e.target.checked)}
                />{" "}
                Show baseline ghost
              </label>
              <label className="range-label" htmlFor="ghost-opacity">
                Ghost opacity <span>{Math.round(ghostOpacity * 100)}%</span>
              </label>
              <input
                id="ghost-opacity"
                type="range"
                min=".15"
                max=".65"
                step=".05"
                value={ghostOpacity}
                disabled={!ghost || !cityReplay || world === "baseline"}
                onChange={(e) => setGhostOpacity(Number(e.target.value))}
              />
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={follow}
                  disabled={!cityReplay || reducedMotion}
                  onChange={(e) => setFollow(e.target.checked)}
                />{" "}
                Follow AFTERLIGHT ambulance
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={reducedMotion}
                  disabled={prefersReduced}
                  onChange={(e) => setMotionOff(e.target.checked)}
                />{" "}
                Reduced motion
              </label>
              <label htmlFor="quality">Rendering quality</label>
              <select
                id="quality"
                value={quality}
                onChange={(e) =>
                  setQuality(e.target.value as "balanced" | "high")
                }
              >
                <option value="balanced">Balanced · lower GPU use</option>
                <option value="high">High resolution</option>
              </select>
            </div>
            <p className="research-note">
              A simulation research instrument.
              <br />
              Not a deployed traffic-control system.
            </p>
          </aside>
          <div className="stage-column">
            <div className="stage-toolbar">
              <div>
                <span className="stage-title">
                  {replay
                    ? world === "afterlight"
                      ? "AFTERLIGHT world"
                      : "Ordinary baseline world"
                    : "The original city"}
                </span>
                <span className="stage-subtitle">
                  {replay
                    ? `Seed ${replay.scenario.seed} · ${replay.worlds[world].policy}`
                    : "25 primary junctions · two hospitals"}
                </span>
              </div>
              <div className="stage-actions">
                <div className="segmented" aria-label="Inspect traffic world">
                  <button
                    aria-pressed={world === "afterlight"}
                    disabled={!replay}
                    onClick={() => setWorld("afterlight")}
                  >
                    Afterlight
                  </button>
                  <button
                    aria-pressed={world === "baseline"}
                    disabled={!replay}
                    onClick={() => setWorld("baseline")}
                  >
                    Baseline
                  </button>
                </div>
                <button
                  className="icon-button"
                  aria-label="Reset camera to city overview"
                  title="Reset camera"
                  onClick={() => {
                    setFollow(false);
                    setReset((x) => x + 1);
                  }}
                >
                  <Icon name="expand" />
                </button>
              </div>
            </div>
            <div className="stage">
              {replay && !cityReplay ? (
                <div className="fixture-view">
                  <h2>
                    {replay.scenario.network_kind === "fixture"
                      ? "Three-junction correctness fixture"
                      : "City geometry is not verified"}
                  </h2>
                  <p>
                    {replay.scenario.network_kind === "fixture"
                      ? "This recording uses a different network. It is not overlaid on the city."
                      : "The recording’s canonical map fingerprint does not match the loaded city. Traffic overlay is disabled to avoid presenting the wrong roads."}
                  </p>
                  <p>
                    Inspect the genuine paired outcomes below. Full-city
                    playback appears only for a recording explicitly exported
                    from the canonical city.
                  </p>
                  <div className="fixture-clock">
                    {time.toFixed(1)} <span>simulation seconds</span>
                  </div>
                </div>
              ) : (
                <CanvasBoundary>
                  <Suspense
                    fallback={
                      <div className="canvas-status" role="status">
                        Loading the 3D renderer…
                      </div>
                    }
                  >
                    <CityView
                      city={city}
                      frames={cityReplay ? replay!.worlds[world].frames : []}
                      baselineFrames={
                        cityReplay ? replay!.worlds.baseline.frames : []
                      }
                      followFrames={
                        cityReplay ? replay!.worlds.afterlight.frames : []
                      }
                      onManualCamera={() => setFollow(false)}
                      clock={playbackClock}
                      routeEdges={replay?.scenario.route_edges ?? []}
                      networkGeometry={replay?.network_geometry?.signals ?? []}
                      ghost={ghost}
                      ghostOpacity={ghostOpacity}
                      pickup={pickup}
                      hospital={hospital}
                      quality={quality}
                      follow={follow}
                      reducedMotion={reducedMotion}
                      reset={reset}
                      world={world}
                    />
                  </Suspense>
                </CanvasBoundary>
              )}
              <div className="map-location">
                <span>
                  {pickup} → {activeHospital?.name ?? hospital}
                </span>
                <small>
                  {replay
                    ? "Both worlds share the same absolute simulation clock."
                    : "Map inspection only · no traffic is being simulated"}
                </small>
              </div>
              {loading && (
                <div className="stage-notice" role="status">
                  <strong>Loading paired recording</strong>
                  <p>Fetching both worlds and checking their time contract.</p>
                  <button onClick={() => setSelection("")}>
                    Cancel loading
                  </button>
                </div>
              )}
              {loadError && (
                <div className="stage-notice error" role="alert">
                  <strong>Recording unavailable</strong>
                  <p>{loadError}</p>
                  <button onClick={() => setLoadRetry((x) => x + 1)}>
                    Retry recording
                  </button>
                  <button onClick={() => setSelection("")}>
                    Return to city
                  </button>
                </div>
              )}
            </div>
            <div className="legend">
              <span>
                <i className="legend-solid" />
                Solid:{" "}
                {world === "afterlight"
                  ? "AFTERLIGHT"
                  : "ordinary baseline"}{" "}
                world
              </span>
              {world === "afterlight" ? (
                <span>
                  <i className="legend-ghost" />
                  Ghost: baseline, separate traffic world
                </span>
              ) : (
                <span>Baseline traffic & signals · ghost hidden</span>
              )}
              <details>
                <summary>Why a ghost?</summary>
                <p>
                  The cyan ambulance is the actual ordinary-baseline trajectory
                  from an independent simulation. It can overlap visible cars or
                  red signals because their traffic worlds differ. It never
                  controls traffic here. Inspect Baseline to see its own world.
                </p>
              </details>
            </div>
            <div className="transport">
              <button
                className="play-button"
                disabled={!replay || loading}
                onClick={() => {
                  if (time >= timelineMax) seekTime(0);
                  else if (playing) setTime(playbackClock.current);
                  setPlaying(!playing);
                }}
                aria-label={playing ? "Pause recording" : "Play recording"}
              >
                <Icon name={playing ? "pause" : "play"} />
                <span>{playing ? "Pause" : "Play"}</span>
              </button>
              <button
                className="icon-button"
                aria-label="Restart recording"
                disabled={!replay}
                onClick={() => {
                  seekTime(0);
                  setPlaying(false);
                }}
              >
                <Icon name="reset" />
              </button>
              <div className="timeline">
                <div className="timeline-label">
                  <label htmlFor="timeline">Absolute simulation time</label>
                  <output htmlFor="timeline">
                    {time.toFixed(1)}{" "}
                    <span>
                      / {replay ? replay.duration_s.toFixed(1) : "—"} s
                    </span>
                  </output>
                </div>
                <input
                  id="timeline"
                  type="range"
                  min="0"
                  max={timelineMax}
                  step=".1"
                  value={time}
                  disabled={!replay}
                  onChange={(e) => {
                    setPlaying(false);
                    seekTime(Number(e.target.value));
                  }}
                />
              </div>
              <label className="speed-control">
                <span>Speed</span>
                <select
                  value={speed}
                  onChange={(e) => setSpeed(Number(e.target.value))}
                  disabled={!replay}
                >
                  {[0.5, 1, 2, 4].map((s) => (
                    <option key={s} value={s}>
                      {s}×
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </section>
        <section className="evidence" aria-labelledby="evidence-title">
          <div className="evidence-heading">
            <h2 id="evidence-title">The aftermath matters.</h2>
            <p>
              {replay
                ? "Measured outcomes from this paired recording. A single run is not a benchmark."
                : "An ambulance arriving sooner is only half the story. Civilian delay and unfinished demand belong in the same comparison."}
            </p>
          </div>
          {replay ? (
            <>
              <div className="evidence-table-wrap">
                <table>
                  <caption>Paired run outcomes · {replay.scenario.id}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Measure</th>
                      <th scope="col">AFTERLIGHT</th>
                      <th scope="col">Ordinary baseline</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <th scope="row">Run status</th>
                      <td>{replay.worlds.afterlight.status}</td>
                      <td>{replay.worlds.baseline.status}</td>
                    </tr>
                    {Array.from(
                      new Set([
                        ...Object.keys(replay.worlds.afterlight.metrics),
                        ...Object.keys(replay.worlds.baseline.metrics),
                      ]),
                    )
                      .filter((key) => {
                        const a = replay.worlds.afterlight.metrics[key],
                          b = replay.worlds.baseline.metrics[key];
                        return (
                          (a == null || typeof a !== "object") &&
                          (b == null || typeof b !== "object")
                        );
                      })
                      .map((key) => (
                        <tr key={key}>
                          <th scope="row">{key.replace(/_/g, " ")}</th>
                          {(["afterlight", "baseline"] as const).map((w) => (
                            <td key={w}>
                              {formatMetric(replay.worlds[w].metrics[key])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    {[
                      "scheduled",
                      "inserted",
                      "completed",
                      "running",
                      "not_inserted",
                    ].map((key) => (
                      <tr key={key}>
                        <th scope="row">
                          Civilians · {key.replace(/_/g, " ")}
                        </th>
                        {(["afterlight", "baseline"] as const).map((w) => (
                          <td key={w}>
                            {formatMetric(
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
              {(["afterlight", "baseline"] as const).some(
                (w) => replay.worlds[w].status !== "completed",
              ) && (
                <p className="outcome-caveat">
                  This pair includes incomplete or invalid outcomes. These are
                  retained as evidence, not treated as a finite comparable
                  completion benefit.
                </p>
              )}
              <QueueChart replay={replay} />
              <DecisionInspector replay={replay} />
              <details className="provenance">
                <summary>Signal phase states at {time.toFixed(1)} s</summary>
                <p>
                  Each character describes one controlled link, not an entire
                  junction. Movement arrows use the exported lane endpoints and
                  exact controlled-link states. Mint is green, amber is yellow,
                  salmon is red. A neutral marker is used when link geometry is
                  unavailable.
                </p>
                <dl>
                  {(replay
                    ? frameAt(replay.worlds[world].frames, time)?.signals
                    : []
                  )?.map((s) => (
                    <div key={s.id}>
                      <dt>{s.id}</dt>
                      <dd>{s.state}</dd>
                    </div>
                  ))}
                </dl>
              </details>
              <details className="provenance">
                <summary>Recording provenance & reproducibility</summary>
                <dl>
                  {Object.entries(replay.provenance).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replace(/_/g, " ")}</dt>
                      <dd>{formatMetric(value)}</dd>
                    </div>
                  ))}
                </dl>
                <p>
                  Dispatch at {seconds(replay.scenario.dispatch_s)}. Playback
                  uses sampled recorded states; visual presentation does not
                  recalculate outcomes.
                </p>
              </details>
            </>
          ) : (
            <div className="evidence-empty">
              <div>
                <span className="empty-rule" />
                <h3>No outcome claims yet</h3>
                <p>
                  Real paired traces, full demand accounting and held-out
                  comparisons are required before publishing a benefit.
                </p>
              </div>
              <a
                href="https://github.com/JunaidAhamed-7777/afterlight/blob/main/docs/BENCHMARK_PROTOCOL.md"
                target="_blank"
                rel="noreferrer"
              >
                Read the evaluation protocol <Icon name="arrow" />
              </a>
            </div>
          )}
        </section>
      </main>
      <footer>
        <span>AFTERLIGHT · Original city, inspectable evidence.</span>
        <span>
          {apiBase ? "Local library connection" : "Static viewer"} · No paid
          backend required
        </span>
      </footer>
    </div>
  );
}
function formatMetric(v: unknown): string {
  if (v === null || v === undefined) return "Not available";
  if (typeof v === "number")
    return Number.isFinite(v)
      ? Number.isInteger(v)
        ? String(v)
        : v.toFixed(2)
      : "Not available";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
