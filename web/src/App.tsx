import { boundedJson } from "./response.ts";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
const CityView = lazy(() =>
  import("./CityView.tsx").then((module) => ({ default: module.CityView })),
);
import { bindRecording, loadRecording } from "./recording.ts";
import { LocalGeneration } from "./LocalGeneration.tsx";
import { CanvasBoundary } from "./CanvasBoundary.tsx";
import { loadCanonicalCity, geometryMatches } from "./city.ts";
import { selectionLabel } from "./selectionEvidence.ts";
import { ReplayEvidence } from "./ReplayEvidence.tsx";
import { StudyResults } from "./StudyResults.tsx";
import { Onboarding } from "./Onboarding.tsx";
import { recordingUrl, validateCatalog } from "./catalog.ts";
import { frameAt } from "./replay.ts";
import type { MapPickMode } from "./MapSelectionLayer.ts";
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
  return boundedJson(r);
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
  const [tourRequest, setTourRequest] = useState(0);
  const [followTarget, setFollowTarget] = useState<"ambulance" | "ghost">("ambulance");
  const [panel, setPanel] = useState<"run" | "results" | "settings">("run");
  const [resultScope, setResultScope] = useState<"recording" | "study">("recording");
  const [bootDismissed, setBootDismissed] = useState(false);
  const [assetLoad, setAssetLoad] = useState({
    completed: 0,
    total: 5,
    phase: "Preparing renderer",
    error: false,
  });
  const settingsScroll = useRef<HTMLDivElement>(null);
  const openedInitialRecording = useRef(false);
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
    [locate, setLocate] = useState(0),
    [reset, setReset] = useState(0),
    [motionOff, setMotionOff] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [selectionLocked, setSelectionLocked] = useState(Boolean(apiBase));
  const [mapReady, setMapReady] = useState(false);
  const [mapPickMode, setMapPickMode] = useState<MapPickMode>(null);
  const [mapSelectionNotice, setMapSelectionNotice] = useState("");
  const mapPickTrigger = useRef<HTMLButtonElement | null>(null);
  const cancelMapPick = () => {
    setMapPickMode(null);
    setMapSelectionNotice("Map selection canceled. Journey unchanged.");
    mapPickTrigger.current?.focus();
  };
  const mapPickingBlocked = Boolean(
    !city || !mapReady || replay || loading || selectionLocked,
  );
  useEffect(() => {
    if (mapPickingBlocked) {
      setMapPickMode(null);
      setMapSelectionNotice("");
    }
  }, [mapPickingBlocked]);
  useEffect(() => {
    if (!mapPickMode) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMapPickMode(null);
        setMapSelectionNotice("Map selection canceled. Journey unchanged.");
        mapPickTrigger.current?.focus();
      }
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [mapPickMode]);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const generatedReplays = useRef(new Map<string, Replay>());
  const playbackClock = useRef(0);
  const seekTime = (t: number) => {
    playbackClock.current = t;
    setTime(t);
  };
  const prefersReduced = useReducedMotion(),
    reducedMotion = prefersReduced || motionOff;
  useEffect(() => {
    const evidenceOnly = Boolean(
      replay &&
        cityHash &&
        (replay.scenario.network_kind !== "city" ||
          !geometryMatches(replay.provenance.canonical_map_sha256, cityHash)),
    );
    if (catalogLoaded && (mapReady || evidenceOnly)) setBootDismissed(true);
  }, [mapReady, catalogLoaded, replay, cityHash]);
  useEffect(() => {
    // Start in a real, inspectable run when the public library supplies one.
    if (
      !catalogLoaded ||
      !catalog.length ||
      apiBase ||
      openedInitialRecording.current
    )
      return;
    openedInitialRecording.current = true;
    const requested = new URLSearchParams(location.search).get("run");
    const first = catalog.find((item) => item.id === requested) ?? catalog[0];
    setSelection(first.id);
  }, [catalog, catalogLoaded]);
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
    setCatalogLoaded(false);
    setCatalogStatus("Loading available recordings…");
    json(source, c.signal)
      .then((d) => {
        if (c.signal.aborted) return;
        const runs = validateCatalog(d, catalogBase);
        setCatalog(runs);
        setCatalogLoaded(true);
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
          bindRecording(generatedReplays.current.get(selection)!, item),
        )
      : loadRecording(item, url, c.signal)
    )
      .then((r) => {
        if (!c.signal.aborted) {
          setReplay(r);
          setPickup(r.scenario.pickup_id);
          setHospital(r.scenario.hospital_id);
          seekTime(r.scenario.dispatch_s);
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
  const pickups = useMemo(
    () =>
      city?.pickups.filter((x) =>
        `${x.id} ${x.road_id}`.toLowerCase().includes(search.toLowerCase()),
      ) ?? [],
    [city, search],
  );
  const changeRoute = (p: string, h: string) => {
    setMapPickMode(null);
    setPickup(p);
    setHospital(h);
    setSelection("");
    setReplay(null);
    setPlaying(false);
    seekTime(0);
  };
  const selectRecording = (id: string) => {
    if (id && id === selection) return;
    setMapPickMode(null);
    setSelection(id);
    setReplay(null);
    setPlaying(false);
    seekTime(0);
    setLoadError("");
    setLoading(Boolean(id));
  };
  const activeHospital = city?.hospitals.find((x) => x.id === hospital);
  const timelineMax = replay?.duration_s ?? 1;
  const activeFrame =
    cityReplay && replay ? frameAt(replay.worlds[world].frames, time) : null;
  const primaryJunctions =
    city?.primary_intersection_count ??
    city?.nodes.filter((node) => node.signalized).length ??
    0;
  const completedLoads =
    assetLoad.completed + (city ? 1 : 0) + (catalogLoaded ? 1 : 0);
  const totalLoads = assetLoad.total + 2;
  const tourReady = bootDismissed && cityReplay && !loading && mapReady;
  const switchPanel = (next: typeof panel) => {
    setPanel(next);
    settingsScroll.current?.scrollTo({ top: 0 });
  };
  const showRecordingResults = () => {
    setResultScope("recording");
    switchPanel("results");
  };
  const togglePlayback = () => {
    if (!replay || loading) return;
    if (time >= timelineMax) seekTime(0);
    else if (playing) setTime(playbackClock.current);
    setPlaying(!playing);
  };
  const followVehicle = (target: "ambulance" | "ghost") => {
    if (!cityReplay || reducedMotion) return;
    const active = follow && followTarget === target;
    setFollowTarget(target);
    setFollow(!active);
    if (target === "ghost" && !active) {
      setGhost(true);
      setWorld("afterlight");
    }
    if (!active) setLocate(value => value + 1);
  };
  const inspectWorld = (next: typeof world) => {
    if (next === world) return;
    setWorld(next);
    setFollow(false);
  };
  return (
    <div className="app-shell">
      <a className="skip-link" href="#experiment-controls">
        Skip to controls
      </a>
      <a className="skip-link" href="#city-workspace">
        Skip to city and playback
      </a>
      <header className="topbar" inert={!bootDismissed}>
        <a className="wordmark" href={base} aria-label="AFTERLIGHT home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          AFTERLIGHT<span className="wordmark-stop">.</span>
        </a>
        <span className="product-label">Traffic signal lab</span>
        <div className="topbar-right">
          <span className="mode-label">
            <span className={`status-dot ${replay ? "recorded" : ""}`} />
            {generating
              ? "Generating locally"
              : replay
                ? "Recorded simulation"
                : "City explorer"}
          </span>
          <a
            className="source-link"
            href="https://github.com/JunaidAhamed-7777/afterlight"
            target="_blank"
            rel="noreferrer"
          >
            Source <Icon name="arrow" />
          </a>
        </div>
      </header>
      <main inert={!bootDismissed}>
        <section className="workspace" aria-label="Traffic experiment">
          <aside className="sidebar" id="experiment-controls" tabIndex={-1}>
            <nav className="panel-nav" aria-label="Workspace sections">
              {(
                [
                  ["run", "Simulation"],
                  ["results", "Results"],
                  ["settings", "Settings"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  data-tour={id === "results" ? "results" : undefined}
                  aria-pressed={panel === id}
                  onClick={() => switchPanel(id)}
                >
                  {label}
                  {id === "results" && replay && <span className="nav-dot" />}
                </button>
              ))}
            </nav>
            <div
              className="settings-scroll"
              ref={settingsScroll}
              role="region"
              aria-label="Experiment settings and evidence"
              tabIndex={0}
            >
              <div className="control-panel" hidden={panel !== "run"}>
                <div className="section-heading">
                  <span className="eyebrow">Ambulance priority</span>
                  <h1>
                    Same city.
                    <br />
                    Different signals.
                  </h1>
                  <p>Watch the journey. Compare the traffic left behind.</p>
                </div>
                {cityError && (
                  <div className="inline-error" role="alert">
                    <p>{cityError}</p>
                    <button onClick={() => setCityRetry((x) => x + 1)}>
                      Retry city map
                    </button>
                  </div>
                )}
                <section
                  className="recording-control"
                  aria-labelledby="recordings-title"
                >
                  <div className="label-row">
                    <h2 id="recordings-title">Recordings</h2>
                    <span className="count-label">{catalog.length}</span>
                  </div>
                  {catalog.length > 0 ? (
                    <div className="recording-list">
                      {catalog.map((r) => (
                        <button
                          key={r.id}
                          className={`recording-card ${selection === r.id ? "selected" : ""}`}
                          aria-pressed={selection === r.id}
                          disabled={loading && selection !== r.id}
                          onClick={() => selectRecording(r.id)}
                        >
                          <span
                            className="recording-card-icon"
                            aria-hidden="true"
                          >
                            <Icon name="play" />
                          </span>
                          <span>
                            <strong>{r.title}</strong>
                            <small>
                              {r.pickup_id} →{" "}
                              {city?.hospitals.find(
                                (h) => h.id === r.hospital_id,
                              )?.name ?? r.hospital_id}
                            </small>
                            <span className="recording-tags">
                              {r.policy_label ?? r.policy.replace(/_/g, " ")}{" "}
                              <span>·</span> seed {r.seed}
                            </span>
                          </span>
                          <span className="recording-check" aria-hidden="true">
                            {selection === r.id ? "✓" : "›"}
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">
                      <strong>
                        {catalogError
                          ? "Library unavailable"
                          : "Explore the city"}
                      </strong>
                      <p>
                        {catalogError
                          ? catalogStatus
                          : apiBase
                            ? "Choose a journey below and generate a paired run."
                            : "No recordings are published yet. Drag the map to explore, or use the camera controls."}
                      </p>
                    </div>
                  )}
                  {catalogError && (
                    <button onClick={() => setCatalogRetry((x) => x + 1)}>
                      Retry library
                    </button>
                  )}
                  {!catalogLoaded && !catalogError && (
                    <p className="field-note" role="status">
                      Loading recordings…
                    </p>
                  )}
                </section>
                {replay && (
                  <section className="run-overview">
                    <div className="label-row">
                      <h2>Current run</h2>
                      <span className="small-badge">Recorded</span>
                    </div>
                    <dl className="run-facts">
                      <div>
                        <dt>Dispatch</dt>
                        <dd>{replay.scenario.dispatch_s.toFixed(0)} s</dd>
                      </div>
                      <div>
                        <dt>Duration</dt>
                        <dd>{replay.duration_s.toFixed(0)} s</dd>
                      </div>
                      <div>
                        <dt>Demand</dt>
                        <dd>
                          {replay.scenario.regime?.replace(/_/g, " ") ??
                            "Recorded"}
                        </dd>
                      </div>
                    </dl>
                    <button
                      className="text-button"
                      onClick={showRecordingResults}
                    >
                      View measured results <Icon name="arrow" />
                    </button>
                  </section>
                )}
                <details
                  className="route-control disclosure"
                  open={!catalog.length || Boolean(apiBase)}
                >
                  <summary>
                    {replay ? "Explore another journey" : "Choose a journey"}
                  </summary>
                  <p>
                    Pick a curb location and destination.{" "}
                    {apiBase
                      ? "The local runner can generate this journey."
                      : "Traffic playback is available for the recordings above."}
                  </p>
                  {replay && (
                    <button
                      className="new-journey"
                      onClick={() => selectRecording("")}
                    >
                      Leave recording & explore
                    </button>
                  )}
                  <label htmlFor="pickup-search">Find a pickup</label>
                  <div className="search-field">
                    <input
                      id="pickup-search"
                      type="search"
                      placeholder="Pickup ID or street"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      autoComplete="off"
                    />
                    {search && (
                      <button
                        className="search-clear"
                        aria-label="Clear pickup search"
                        onClick={() => {
                          setSearch("");
                          document.getElementById("pickup-search")?.focus();
                        }}
                      >
                        ×
                      </button>
                    )}
                  </div>
                  <label htmlFor="pickup">Pickup point</label>
                  <select
                    id="pickup"
                    value={pickup}
                    onChange={(e) => changeRoute(e.target.value, hospital)}
                    disabled={!city || Boolean(replay)}
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
                      ? `${pickups.length} of ${city.pickups.length} pickup locations`
                      : "Loading map…"}
                    {city && !pickups.length
                      ? " · No matches. Try a pickup ID such as P001."
                      : ""}
                  </span>
                  <label htmlFor="hospital">Destination hospital</label>
                  <select
                    id="hospital"
                    value={hospital}
                    onChange={(e) => changeRoute(pickup, e.target.value)}
                    disabled={!city || Boolean(replay)}
                  >
                    {city?.hospitals.map((h) => (
                      <option key={h.id} value={h.id}>
                        {h.name ?? h.id}
                      </option>
                    ))}
                  </select>
                  <div className="map-selection-actions">
                    {(
                      [
                        ["pickup", "Pick on map"],
                        ["hospital", "Hospital on map"],
                      ] as const
                    ).map(([mode, label]) => (
                      <button
                        key={mode}
                        disabled={mapPickingBlocked}
                        aria-pressed={mapPickMode === mode}
                        onClick={(event) => {
                          mapPickTrigger.current = event.currentTarget;
                          setMapPickMode(mode);
                          setMapSelectionNotice(
                            `Choose a ${mode} marker on the map.`,
                          );
                        }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {replay && (
                    <p className="field-note">
                      Leave the recording to change its journey.
                    </p>
                  )}
                  <span className="sr-only" role="status">
                    {mapSelectionNotice}
                  </span>
                </details>
              </div>
              {apiBase && (
                <div hidden={panel !== "run"} className="generation-wrap">
                  <LocalGeneration
                    apiBase={apiBase}
                    pickup={pickup}
                    hospital={hospital}
                    mapReady={Boolean(city)}
                    onBusy={setGenerating}
                    onSelectionLocked={setSelectionLocked}
                    onStarted={() => {
                      setMapPickMode(null);
                      setSelection("");
                      setReplay(null);
                      setPlaying(false);
                      seekTime(0);
                    }}
                    onOpen={(r, url) => {
                      generatedReplays.current.clear();
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
                </div>
              )}
              <div hidden={panel !== "results"}>
                <div className="results-scope" role="group" aria-label="Results scope">
                  <button aria-pressed={resultScope === "recording"} onClick={() => { setResultScope("recording"); settingsScroll.current?.scrollTo({ top: 0 }); }}>This run</button>
                  <button aria-pressed={resultScope === "study"} onClick={() => { setResultScope("study"); settingsScroll.current?.scrollTo({ top: 0 }); }}>Study</button>
                </div>
                {resultScope === "study" ? (
                  panel === "results" && <StudyResults />
                ) : replay ? (
                  <ReplayEvidence replay={replay} />
                ) : (
                  <div className="control-panel">
                    <div className="section-heading">
                      <span className="eyebrow">Measured evidence</span>
                      <h2>Results follow a run.</h2>
                      <p>
                        Open a recording in Simulation to compare ambulance
                        travel and civilian delay.
                      </p>
                    </div>
                    <button
                      className="primary-button"
                      onClick={() => switchPanel("run")}
                    >
                      Browse recordings <Icon name="arrow" />
                    </button>
                  </div>
                )}
              </div>
              <div className="control-panel" hidden={panel !== "settings"}>
                <div className="section-heading">
                  <span className="eyebrow">Workspace</span>
                  <h2>View settings</h2>
                  <p>Change the view without changing the simulation.</p>
                </div>
                <section className="view-options">
                  <h3>Comparison</h3>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={ghost}
                      disabled={!cityReplay || world === "baseline"}
                      onChange={(e) => {
                        setGhost(e.target.checked);
                        if (!e.target.checked && followTarget === "ghost") setFollow(false);
                      }}
                    />
                    <span>
                      Show baseline ghost
                      <small>
                        Actual ambulance from the ordinary-signal world.
                      </small>
                    </span>
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
                  {!cityReplay && (
                    <p className="field-note">
                      Open a city recording to use comparison controls.
                    </p>
                  )}
                </section>
                <section className="view-options">
                  <h3>Rendering</h3>
                  <label htmlFor="quality">Quality</label>
                  <select
                    id="quality"
                    value={quality}
                    onChange={(e) =>
                      setQuality(e.target.value as "balanced" | "high")
                    }
                  >
                    <option value="balanced">Balanced</option>
                    <option value="high">High resolution</option>
                  </select>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={reducedMotion}
                      disabled={prefersReduced}
                      onChange={(e) => setMotionOff(e.target.checked)}
                    />
                    <span>
                      Reduced motion
                      <small>
                        Disables camera following.
                        {prefersReduced ? " Enabled by your system." : ""}
                      </small>
                    </span>
                  </label>
                </section>
                <section className="view-options">
                  <h3>Quick tour</h3>
                  <p className="field-note" id="tour-availability">
                    {tourReady
                      ? "A short guide to recordings, playback and the two ambulances."
                      : "Open a city recording with the 3D view ready to use the guide."}
                  </p>
                  <button data-tour-reopen className="text-button" disabled={!tourReady} aria-describedby="tour-availability" onClick={() => setTourRequest(value => value + 1)}>Show the guide <Icon name="arrow" /></button>
                </section>
                <section className="view-options">
                  <h3>Camera shortcuts</h3>
                  <dl className="shortcut-list">
                    <div>
                      <dt>Orbit</dt>
                      <dd>Drag</dd>
                    </div>
                    <div>
                      <dt>Zoom</dt>
                      <dd>Scroll / + −</dd>
                    </div>
                    <div>
                      <dt>Pan</dt>
                      <dd>Arrow keys / right drag</dd>
                    </div>
                    <div>
                      <dt>Tilt, heading, roll</dt>
                      <dd>X / Y / Z</dd>
                    </div>
                    <div>
                      <dt>Reverse rotation</dt>
                      <dd>Shift + X / Y / Z</dd>
                    </div>
                    <div>
                      <dt>Full city</dt>
                      <dd>0</dd>
                    </div>
                  </dl>
                  <p className="field-note">
                    Focus the map before using camera keys. Tab moves to the
                    next control.
                  </p>
                </section>
                <details className="disclosure">
                  <summary>About this experiment</summary>
                  <p>
                    AFTERLIGHT compares ambulance priority with ordinary traffic
                    signals in SUMO. Its ghost belongs to an independent world;
                    it may overlap the visible traffic.
                  </p>
                  <p>
                    This is simulation research. It is not a deployed traffic
                    controller.
                  </p>
                  <a
                    href="https://github.com/JunaidAhamed-7777/afterlight/blob/main/docs/BENCHMARK_PROTOCOL.md"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Evaluation protocol ↗
                  </a>
                </details>
              </div>
              <footer>
                <span>Built with SUMO · Original Blender city</span>
                <a
                  href="https://github.com/JunaidAhamed-7777/afterlight"
                  target="_blank"
                  rel="noreferrer"
                >
                  Method & source ↗
                </a>
              </footer>
            </div>
          </aside>
          <div
            className="stage-column"
            id="city-workspace"
            role="region"
            aria-label="City view and playback"
            tabIndex={-1}
          >
            <div className="stage-toolbar">
              <div className="stage-heading">
                <span className="eyebrow">
                  {replay ? "Paired simulation" : "City explorer"}
                </span>
                <span className="stage-title">
                  {replay
                    ? (catalog.find((r) => r.id === selection)?.title ??
                      "Recorded journey")
                    : "Afterlight City"}
                </span>
              </div>
              <div className="stage-actions">
                {replay && (
                  <div className="segmented" aria-label="Inspect traffic world">
                    <button
                      aria-pressed={world === "afterlight"}
                      onClick={() => inspectWorld("afterlight")}
                    >
                      Afterlight
                    </button>
                    <button
                      aria-pressed={world === "baseline"}
                      onClick={() => inspectWorld("baseline")}
                    >
                      Ordinary
                    </button>
                  </div>
                )}
                <button
                  className="icon-button"
                  aria-label="Reset camera to city overview"
                  title="Full city"
                  onClick={() => {
                    setFollow(false);
                    setReset((x) => x + 1);
                  }}
                >
                  <Icon name="expand" />
                </button>
              </div>
            </div>
            <div className="map-location">
              <span className="journey">
                <span className="route-origin" />
                {pickup}
                <Icon name="arrow" />
                <span className="hospital-cross" aria-hidden="true">
                  +
                </span>
                {activeHospital?.name ?? hospital}
              </span>
              <span className="stage-subtitle">
                {replay
                  ? `Seed ${replay.scenario.seed} · ${world === "afterlight" && replay.selection_evidence ? selectionLabel(replay.selection_evidence) : replay.worlds[world].policy.replace(/_/g, " ")}`
                  : `${primaryJunctions} intersections · 2 hospitals`}
              </span>
            </div>
            <div className="stage">
              {replay && !cityReplay ? (
                <div className="fixture-view">
                  <span className="eyebrow">Recording geometry</span>
                  <h2>
                    {replay.scenario.network_kind === "fixture"
                      ? "Three-junction fixture"
                      : "This recording uses another map."}
                  </h2>
                  <p>
                    {replay.scenario.network_kind === "fixture"
                      ? "A separate network for checking signal control. Its outcomes are available in Results."
                      : "Traffic is hidden because this recording does not match the current city. Open Results to inspect the saved outcomes."}
                  </p>
                  <button onClick={showRecordingResults}>
                    Inspect results <Icon name="arrow" />
                  </button>
                  <div className="fixture-clock">
                    {time.toFixed(1)}
                    <small>simulation seconds</small>
                  </div>
                </div>
              ) : (
                <CanvasBoundary
                  onFailure={() =>
                    setAssetLoad((state) => ({
                      ...state,
                      error: true,
                      phase: "The 3D renderer could not start",
                    }))
                  }
                >
                  <Suspense
                    fallback={
                      <div className="canvas-status" role="status">
                        Preparing the 3D renderer…
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
                        cityReplay ? replay!.worlds[followTarget === "ghost" ? "baseline" : world].frames : []
                      }
                      onManualCamera={() => setFollow(false)}
                      onMapReady={setMapReady}
                      onLoadState={setAssetLoad}
                      pickMode={mapPickingBlocked ? null : mapPickMode}
                      onCancelPick={cancelMapPick}
                      onMapPick={(mode, id) => {
                        if (mapPickingBlocked || mode !== mapPickMode || !city)
                          return;
                        if (
                          mode === "pickup" &&
                          city.pickups.some((point) => point.id === id)
                        ) {
                          changeRoute(id, hospital);
                          setMapSelectionNotice(`Pickup ${id} selected.`);
                        } else if (
                          mode === "hospital" &&
                          city.hospitals.some((point) => point.id === id)
                        ) {
                          changeRoute(pickup, id);
                          setMapSelectionNotice(
                            `${city.hospitals.find((point) => point.id === id)?.name ?? id} selected.`,
                          );
                        } else return;
                        mapPickTrigger.current?.focus();
                      }}
                      clock={playbackClock}
                      routeEdges={replay?.scenario.route_edges ?? []}
                      networkGeometry={replay?.network_geometry?.signals ?? []}
                      signalWorld={cityReplay ? replay!.worlds[world] : null}
                      ghost={ghost}
                      ghostOpacity={ghostOpacity}
                      pickup={pickup}
                      hospital={hospital}
                      quality={quality}
                      follow={follow}
                      playing={playing}
                      followTarget={followTarget}
                      canFollow={cityReplay && !reducedMotion}
                      onFollow={followVehicle}
                      reducedMotion={reducedMotion}
                      reset={reset}
                      locate={locate}
                      world={world}
                    />
                  </Suspense>
                </CanvasBoundary>
              )}
              {cityReplay && (
                <div
                  className="scene-readout"
                  aria-label="Current traffic state"
                >
                  <span>
                    <strong>
                      {activeFrame?.vehicles.filter(
                        (v) => v.type !== "ambulance",
                      ).length ?? 0}
                    </strong>{" "}
                    on the road
                  </span>
                  <span>
                    <strong>{activeFrame?.queue_count ?? 0}</strong> queued
                  </span>
                </div>
              )}
              {loading && (
                <div className="stage-notice" role="status">
                  <span className="loader-ring" />
                  <strong>Loading recording</strong>
                  <p>Loading both traffic worlds.</p>
                  <button onClick={() => setSelection("")}>Cancel</button>
                </div>
              )}
              {loadError && (
                <div className="stage-notice error" role="alert">
                  <strong>Recording unavailable</strong>
                  <p>{loadError}</p>
                  <div className="button-row">
                    <button onClick={() => setLoadRetry((x) => x + 1)}>
                      Retry recording
                    </button>
                    <button onClick={() => setSelection("")}>
                      Explore city
                    </button>
                  </div>
                </div>
              )}
            </div>
            {cityReplay && (
              <div className="legend">
                <span>
                  <img className="legend-model" src={`${base}assets/previews/ambulance_model.png`} alt="" />
                  {world === "afterlight"
                    ? "Afterlight ambulance"
                    : "Ordinary ambulance"}
                </span>
                {world === "afterlight" && ghost && (
                  <span>
                    <img className="legend-model" src={`${base}assets/previews/ghost_model.png`} alt="" />
                    Baseline ghost
                  </span>
                )}
                <details>
                  <summary>Two traffic worlds</summary>
                  <p>
                    The ghost is the actual ambulance from the ordinary-signal
                    run. Its cars and signals belong to a separate simulation.
                    Switch to Ordinary to inspect that world.
                  </p>
                </details>
              </div>
            )}
            <div className={`transport ${!replay ? "transport-empty" : ""}`}>
              <button
                className="play-button"
                disabled={!replay || loading}
                onClick={togglePlayback}
                aria-label={playing ? "Pause recording" : "Play recording"}
              >
                <Icon name={playing ? "pause" : "play"} />
                <span>{playing ? "Pause" : "Play"}</span>
              </button>
              <button
                className="icon-button"
                title="Restart"
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
                  <label htmlFor="timeline">
                    {replay
                      ? "Simulation time"
                      : "Open a recording to play traffic"}
                  </label>
                  <output htmlFor="timeline">
                    {time.toFixed(1)}{" "}
                    <span>
                      / {replay ? replay.duration_s.toFixed(0) : "—"} s
                    </span>
                  </output>
                </div>
                <div className="timeline-track">
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
                  {replay && (
                    <span
                      className="dispatch-marker"
                      style={{
                        left: `${(replay.scenario.dispatch_s / timelineMax) * 100}%`,
                      }}
                      title={`Dispatch at ${replay.scenario.dispatch_s} s`}
                    />
                  )}
                </div>
              </div>
              <label className="speed-control">
                <span className="sr-only">Playback speed</span>
                <select
                  aria-label="Playback speed"
                  value={speed}
                  onChange={(e) => setSpeed(Number(e.target.value))}
                  disabled={!replay}
                >
                  {[0.5, 1, 2, 4, 10, 20].map((s) => (
                    <option key={s} value={s}>
                      {s}×
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </section>
      </main>
      <Onboarding ready={tourReady} openRequest={tourRequest} onOpen={() => { setTime(playbackClock.current); setPlaying(false); setResultScope("recording"); switchPanel("run"); }} />
      {!bootDismissed && (
        <div
          className="boot-screen"
          role="status"
          aria-live="polite"
          aria-label="Loading Afterlight"
        >
          <div className="boot-content">
            <div className="boot-symbol" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <span className="boot-wordmark">
              AFTERLIGHT<span>.</span>
            </span>
            <h2>
              {assetLoad.error || cityError || catalogError
                ? "The city could not load."
                : "Bringing the city to life."}
            </h2>
            <p>
              {cityError
                ? "City map unavailable"
                : catalogError
                  ? "Recording library unavailable"
                  : assetLoad.phase}
            </p>
            <progress
              aria-label="City loading progress"
              max={totalLoads}
              value={completedLoads}
            />
            <div className="boot-progress-label">
              <span>
                {completedLoads} / {totalLoads} resources ready
              </span>
              <span>3D traffic signal lab</span>
            </div>
            {(assetLoad.error || cityError || catalogError) && (
              <div className="button-row">
                <button onClick={() => location.reload()}>Try again</button>
                <button onClick={() => setBootDismissed(true)}>
                  Open workspace
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
