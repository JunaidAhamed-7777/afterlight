import { memo, useEffect, useId, useMemo, useRef, useState } from "react";
import type { Replay } from "./types.ts";
import type { QueuePoint, QueueSeries, QueueWorld } from "./queueTypes.ts";
import { liveQueueWorld, queueCutoff, queueScale, revealedQueue } from "./queuePlot.ts";
import "./styles/queue.css";

const labels: Record<QueueWorld, string> = { afterlight: "Afterlight", baseline: "Ordinary" };
const seconds = (value: number) => `${value.toFixed(1)} s`;

/** One renderer for recorded playback and actual in-flight simulation samples. */
function QueuePlot({ series, duration, time, world, live, running, status }: {
  series: QueueSeries;
  duration: number;
  time: number | null;
  world: QueueWorld;
  live: boolean;
  running: boolean;
  status?: string;
}) {
  const [compare, setCompare] = useState(false);
  const [width, setWidth] = useState(320);
  const host = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    const node = host.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry.contentRect.width);
      if (next > 0) setWidth(next);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const scale = useMemo(() => queueScale(series), [series]);
  const cursor = time === null
    ? Math.min(duration, series[world].at(-1)?.t ?? 0)
    : queueCutoff(time, duration);
  const visible = useMemo(() => ({
    afterlight: revealedQueue(series.afterlight, time === null ? duration : cursor),
    baseline: revealedQueue(series.baseline, time === null ? duration : cursor),
  }), [series, time, duration, cursor]);
  const worlds: QueueWorld[] = compare ? ["afterlight", "baseline"] : [world];
  const height = 218, left = 38, right = 14, top = 30, bottom = 30;
  const x = (t: number) => left + t / duration * Math.max(1, width - left - right);
  const y = (count: number) => height - bottom - count / scale.maximum * (height - top - bottom);
  const pointList = (points: readonly QueuePoint[]) => points.map((point) => `${x(point.t)},${y(point.queue_count)}`).join(" ");
  const hasSamples = worlds.some((key) => visible[key].length > 0);
  return (
    <figure className={`queue-chart progressive-queue-chart${live ? " live-queues" : ""}`} data-queue-time={cursor} data-queue-world={world}>
      <figcaption>
        <strong>Civilian queues over time</strong>
        <button type="button" className="queue-compare" aria-pressed={compare} onClick={() => setCompare((value) => !value)}>Compare worlds</button>
      </figcaption>
      <dl className="queue-latest">
        {worlds.map((key) => {
          const latest = visible[key].at(-1);
          return <div key={key} className={compare && key === "baseline" ? "comparison" : "selected"}>
            <dt><span aria-hidden="true" />{labels[key]}</dt>
            <dd>{latest ? latest.queue_count : "—"}<small> queued</small></dd>
          </div>;
        })}
      </dl>
      <div className="queue-plot-host" ref={host}>
        <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-labelledby={`${id}-title ${id}-desc`}>
          <title id={`${id}-title`}>{compare ? "Afterlight and ordinary" : labels[world]} civilian queues through {seconds(cursor)}</title>
          <desc id={`${id}-desc`}>Actual sampled counts, not predictions. The time axis stays from zero to {duration} seconds.
            {live ? " Only received simulation samples are drawn." : " Future samples are hidden until playback reaches them; scrubbing back removes later samples."}
            {compare ? " Afterlight is solid amber. Ordinary is dashed cyan." : ` ${labels[world]} is the single amber line.`}
            {worlds.map((key) => { const latest = visible[key].at(-1); return latest ? ` ${labels[key]}: ${latest.queue_count} queued at ${seconds(latest.t)}.` : ` ${labels[key]} has no samples yet.`; }).join("")}
          </desc>
          {scale.ticks.map((tick) => <g key={tick}>
            <line className="queue-grid" x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} vectorEffect="non-scaling-stroke" />
            <text x={left - 9} y={y(tick) + 4} textAnchor="end">{tick}</text>
          </g>)}
          {[0, 1 / 3, 2 / 3, 1].map((fraction) => <text key={fraction} x={x(duration * fraction)} y={height - 8} textAnchor={fraction === 0 ? "start" : fraction === 1 ? "end" : "middle"}>{Math.round(duration * fraction)} s</text>)}
          <line className="queue-cursor" x1={x(cursor)} x2={x(cursor)} y1={top} y2={height - bottom} vectorEffect="non-scaling-stroke" />
          <text className="queue-cursor-label" x={Math.max(left, Math.min(width - right, x(cursor)))} y={top - 12} textAnchor={cursor < duration * .2 ? "start" : cursor > duration * .8 ? "end" : "middle"}>{seconds(cursor)}</text>
          {worlds.map((key) => {
            const points = visible[key], latest = points.at(-1);
            const tone = compare && key === "baseline" ? "comparison" : "selected";
            return <g key={key} className={`queue-series ${tone}`} data-world={key} data-samples={points.length} data-last-time={latest?.t ?? ""} data-last-queue={latest?.queue_count ?? ""}>
              <polyline className={`queue-trace-${key}`} points={pointList(points)} vectorEffect="non-scaling-stroke" />
              {latest && <circle cx={x(latest.t)} cy={y(latest.queue_count)} r="2.5" />}
            </g>;
          })}
          {!hasSamples && <text className="queue-empty" x={(left + width - right) / 2} y={(top + height - bottom) / 2} textAnchor="middle">{live && running ? "Waiting for samples" : "No samples yet"}</text>}
        </svg>
      </div>
      <p className="queue-caption">{live
        ? `${running ? "Calculating" : "Partial calculation"} · ${status || "Actual received samples only"}`
        : "Playback history · actual sampled counts"}</p>
      {!live && <small>Queue counts are not the benchmark recovery metric.</small>}
    </figure>
  );
}

/** The replay's original queue samples, progressively revealed by its clock. */
export const QueueChart = memo(function QueueChart({ replay, time = 0, world = "afterlight" }: {
  replay: Replay;
  time?: number;
  world?: QueueWorld;
}) {
  const series = useMemo<QueueSeries>(() => ({
    afterlight: replay.worlds.afterlight.frames.map(({ t, queue_count }) => ({ t, queue_count })),
    baseline: replay.worlds.baseline.frames.map(({ t, queue_count }) => ({ t, queue_count })),
  }), [replay]);
  return <QueuePlot series={series} duration={replay.duration_s} time={time} world={world} live={false} running={false} />;
});

/** Only samples actually received from the running calculation enter this plot. */
export const LiveQueueChart = memo(function LiveQueueChart({ series, running, status, world, duration = 900 }: {
  series: QueueSeries;
  running: boolean;
  status?: string;
  world?: QueueWorld;
  duration?: number;
}) {
  return <QueuePlot series={series} duration={duration} time={null} world={world ?? liveQueueWorld(series)} live running={running} status={status} />;
});
