import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Replay } from "./types.ts";
import { recordingUrl } from "./catalog.ts";
import { validateReplay } from "./replay.ts";
import {
  generationParameters,
  localRequest,
  LocalResponseError,
  validateJob,
  type GenerationJob,
  storedRequest,
  type StoredRequest,
} from "./generation.ts";
interface Props {
  apiBase: string;
  pickup: string;
  hospital: string;
  mapReady: boolean;
  onStarted: () => void;
  onBusy: (busy: boolean) => void;
  onOpen: (replay: Replay, url: string) => void;
}
export function LocalGeneration(props: Props) {
  const callbacks = useRef(props);
  callbacks.current = props;
  const [available, setAvailable] = useState(false),
    [healthError, setHealthError] = useState(""),
    [healthRetry, setHealthRetry] = useState(0);
  const [seed, setSeed] = useState("7"),
    [regime, setRegime] = useState("moderate"),
    [policy, setPolicy] = useState("fixed"),
    [lead, setLead] = useState(10);
  const [job, setJob] = useState<GenerationJob | null>(null),
    [requesting, setRequesting] = useState(false),
    [uncertain, setUncertain] = useState(false),
    [error, setError] = useState(""),
    [pollError, setPollError] = useState(""),
    [watchRetry, setWatchRetry] = useState(0),
    [ready, setReady] = useState<{ replay: Replay; url: string } | null>(null);
  const [requestRecord, setRequestRecord] = useState<StoredRequest | null>(
    null,
  );
  const pending = useRef(false),
    seedInput = useRef<HTMLInputElement>(null),
    postAbort = useRef<AbortController | null>(null);
  const sessionKey = `afterlight.local-job:${props.apiBase}`;
  const active =
    requesting || job?.status === "queued" || job?.status === "running";
  useEffect(() => () => postAbort.current?.abort(), []);
  useEffect(() => {
    const c = new AbortController();
    setHealthError("");
    localRequest(`${props.apiBase}/api/health`, c.signal)
      .then((value) => {
        if (c.signal.aborted) return;
        const health = value as { generation_available?: boolean };
        setAvailable(health.generation_available === true);
        if (health.generation_available) {
          try {
            const saved = sessionStorage.getItem(sessionKey);
            const record = saved ? storedRequest(JSON.parse(saved)) : null;
            if (record) setRequestRecord(record);
            const id = record?.id;
            if (id)
              localRequest(`${props.apiBase}/api/jobs/${id}`, c.signal)
                .then(validateJob)
                .then((job) => {
                  if (!c.signal.aborted) {
                    setJob(job);
                    setUncertain(false);
                    setPollError("");
                  }
                })
                .catch(() => {
                  if (!c.signal.aborted) {
                    setUncertain(true);
                    setPollError(
                      "The previous job could not be recovered. Its ID is retained; retry the local connection before starting another run.",
                    );
                  }
                });
          } catch {
            /* Storage may be disabled; generation still works in this page. */
          }
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setAvailable(false);
          setHealthError(e.message);
        }
      });
    return () => c.abort();
  }, [props.apiBase, healthRetry, sessionKey]);
  useEffect(() => {
    callbacks.current.onBusy(Boolean(active));
  }, [active]);
  useEffect(() => {
    if (!job?.id) return;
    const c = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setPollError("");
    const poll = async () => {
      try {
        const next = validateJob(
          await localRequest(`${props.apiBase}/api/jobs/${job.id}`, c.signal),
        );
        if (c.signal.aborted) return;
        setJob(next);
        if (next.status === "queued" || next.status === "running") {
          timer = setTimeout(poll, 1500);
          return;
        }
        if (next.status === "completed") {
          if (!next.replay_url)
            throw new Error("The completed job has no replay link.");
          const url = recordingUrl(next.replay_url, `${props.apiBase}/`);
          const replay = validateReplay(await localRequest(url, c.signal));
          if (!c.signal.aborted) setReady({ replay, url });
        }
      } catch (e) {
        if (!c.signal.aborted)
          setPollError(
            e instanceof Error ? e.message : "Local status could not be read.",
          );
      }
    };
    void poll();
    return () => {
      c.abort();
      if (timer) clearTimeout(timer);
    };
  }, [job?.id, props.apiBase, watchRetry]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current || active || uncertain) return;
    setError("");
    let parameters;
    try {
      parameters = generationParameters(
        seed,
        regime,
        policy,
        lead,
        props.pickup,
        props.hospital,
      );
    } catch (e) {
      setError((e as Error).message);
      seedInput.current?.focus();
      return;
    }
    const record = { id: crypto.randomUUID().replaceAll("-", ""), parameters };
    await sendRequest(record);
  }
  async function sendRequest(record: StoredRequest) {
    if (pending.current) return;
    pending.current = true;
    setRequesting(true);
    setUncertain(false);
    setError("");
    setReady(null);
    setPollError("");
    setJob(null);
    setRequestRecord(record);
    try {
      sessionStorage.setItem(sessionKey, JSON.stringify(record));
    } catch {
      /* The request ID also remains in page state. */
    }
    callbacks.current.onStarted();
    const c = new AbortController();
    postAbort.current = c;
    try {
      const result = validateJob(
        await localRequest(`${props.apiBase}/api/runs`, c.signal, {
          request_id: record.id,
          ...record.parameters,
        }),
      );
      if (c.signal.aborted) return;
      if (result.id !== record.id)
        throw new Error("Server returned a different request identity.");
      setJob(result);
    } catch (e) {
      if (c.signal.aborted) return;
      if (
        e instanceof LocalResponseError &&
        e.status >= 400 &&
        e.status < 500
      ) {
        setError(e.message);
        setRequestRecord(null);
        try {
          sessionStorage.removeItem(sessionKey);
        } catch {
          /* Optional browser storage. */
        }
      } else {
        // Read-only recovery first. Never blindly submit a second job after a lost response.
        try {
          const recovered = validateJob(
            await localRequest(
              `${props.apiBase}/api/jobs/${record.id}`,
              c.signal,
            ),
          );
          if (!c.signal.aborted) setJob(recovered);
        } catch {
          if (!c.signal.aborted) {
            setUncertain(true);
            setError(
              "The request response was interrupted. Check its known ID or retry the exact same request below; its saved settings and idempotency key prevent a duplicate job.",
            );
          }
        }
      }
    } finally {
      pending.current = false;
      if (!c.signal.aborted) setRequesting(false);
    }
  }
  if (!available)
    return (
      <div className="local-generation unavailable">
        <h2>Local simulation</h2>
        <p>
          {healthError
            ? "The local runner could not be reached. Recorded files remain available."
            : "New runs are disabled. Start the local server with --enable-generation to run real paired simulations."}
        </p>
        {healthError && (
          <>
            <p className="field-note">{healthError}</p>
            <button onClick={() => setHealthRetry((x) => x + 1)}>
              Retry local connection
            </button>
          </>
        )}
      </div>
    );
  return (
    <section className="local-generation" aria-labelledby="generation-title">
      <h2 id="generation-title">Run a local experiment</h2>
      <p>
        Generate independent SUMO worlds on this computer. No results exist
        until both runs finish.
      </p>
      <form onSubmit={submit} noValidate>
        <fieldset disabled={Boolean(active || uncertain)}>
          <legend className="sr-only">New paired simulation settings</legend>
          <label htmlFor="generation-seed">Random seed</label>
          <input
            ref={seedInput}
            id="generation-seed"
            inputMode="numeric"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            aria-describedby={error ? "generation-error" : undefined}
            aria-invalid={Boolean(error)}
          />
          <label htmlFor="generation-regime">Traffic demand</label>
          <select
            id="generation-regime"
            value={regime}
            onChange={(e) => setRegime(e.target.value)}
          >
            <option value="sparse">Sparse</option>
            <option value="moderate">Moderate</option>
            <option value="asymmetric">Asymmetric</option>
            <option value="heavy">Heavy</option>
          </select>
          <label htmlFor="generation-policy">AFTERLIGHT policy</label>
          <select
            id="generation-policy"
            value={policy}
            onChange={(e) => setPolicy(e.target.value)}
          >
            <option value="fixed">Fixed clearance lead</option>
            <option value="analytical">Analytical · no learned model</option>
            <option value="immediate">Immediate priority</option>
            <option value="ordinary">Ordinary signals · control</option>
          </select>
          {policy === "fixed" && (
            <>
              <label htmlFor="generation-lead">Clearance lead</label>
              <select
                id="generation-lead"
                value={lead}
                onChange={(e) => setLead(Number(e.target.value))}
              >
                {[0, 5, 10, 20, 30].map((n) => (
                  <option value={n} key={n}>
                    {n} seconds
                  </option>
                ))}
              </select>
              <span className="field-note">
                Zero lead requests at predicted arrival, not at dispatch.
              </span>
            </>
          )}
          <button
            className="generate-button"
            type="submit"
            disabled={!props.mapReady}
          >
            {requesting ? "Sending request…" : "Generate paired run"}
          </button>
        </fieldset>
      </form>
      {error && (
        <p id="generation-error" role="alert" className="generation-error">
          {error}
        </p>
      )}
      {uncertain && requestRecord && (
        <div className="generation-recovery">
          <p>
            Saved request: {requestRecord.parameters.pickup} →{" "}
            {requestRecord.parameters.hospital} · seed{" "}
            {requestRecord.parameters.seed} · {requestRecord.parameters.policy}
          </p>
          <button onClick={() => setHealthRetry((x) => x + 1)}>
            Check known request
          </button>
          <button onClick={() => void sendRequest(requestRecord)}>
            Retry exact saved request
          </button>
        </div>
      )}
      {job && (
        <div className="generation-status" role="status">
          <strong>
            {job.status === "completed"
              ? "Execution finished"
              : job.status === "failed"
                ? "Execution failed"
                : job.status === "queued"
                  ? "Queued for SUMO"
                  : "Running both worlds"}
          </strong>
          <p>
            {job.parameters.pickup} → {job.parameters.hospital} · seed{" "}
            {job.parameters.seed}
          </p>
          <p>{job.status === "failed" ? job.error : job.message}</p>
          {active && (
            <small>
              This is local generation, not live-streamed traffic. The server
              continues safely if you leave this page; closing the viewer does
              not cancel a run.
            </small>
          )}
        </div>
      )}
      {pollError && (
        <div role="alert" className="generation-error">
          <p>Status could not be confirmed: {pollError}</p>
          <button
            onClick={() => {
              if (job) setWatchRetry((x) => x + 1);
              else setHealthRetry((x) => x + 1);
            }}
          >
            Retry status
          </button>
        </div>
      )}
      {ready && (
        <button
          className="generate-button"
          onClick={() => callbacks.current.onOpen(ready.replay, ready.url)}
        >
          Open completed recording
        </button>
      )}
    </section>
  );
}
