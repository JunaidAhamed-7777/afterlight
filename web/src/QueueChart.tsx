import { memo } from "react";
import type { Replay } from "./types.ts";
/** Actual per-world queue counts at their original absolute timestamps. */
export const QueueChart = memo(function QueueChart({
  replay,
}: {
  replay: Replay;
}) {
  const worlds = ["afterlight", "baseline"] as const;
  const maxQueue = worlds.reduce(
    (peak, world) =>
      replay.worlds[world].frames.reduce(
        (value, frame) => Math.max(value, frame.queue_count),
        peak,
      ),
    1,
  );
  const width = 680,
    height = 150,
    left = 38,
    right = 12,
    top = 15,
    bottom = 26;
  const x = (t: number) =>
    left + (t / replay.duration_s) * (width - left - right);
  const y = (q: number) =>
    height - bottom - (q / maxQueue) * (height - top - bottom);
  return (
    <figure className="queue-chart">
      <figcaption>
        <strong>Civilian queues over time</strong>
        <span>Actual sampled counts · same absolute window</span>
      </figcaption>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby="queue-chart-title queue-chart-desc"
      >
        <title id="queue-chart-title">
          Civilian queue counts in both independent worlds
        </title>
        <desc id="queue-chart-desc">
          From zero to {replay.duration_s} simulation seconds. Maximum plotted
          queue count {maxQueue}. Afterlight is amber; ordinary baseline is
          dashed cyan. Counts are recorded, not predicted.
        </desc>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line
              x1={left}
              x2={width - right}
              y1={y(maxQueue * f)}
              y2={y(maxQueue * f)}
              className="chart-grid"
            />
            <text x={left - 9} y={y(maxQueue * f) + 4} textAnchor="end">
              {(maxQueue * f).toFixed(f === 0.5 ? 1 : 0)}
            </text>
          </g>
        ))}
        {worlds.map((w) => (
          <polyline
            key={w}
            className={`queue-line ${w}`}
            points={replay.worlds[w].frames
              .map((f) => `${x(f.t)},${y(f.queue_count)}`)
              .join(" ")}
          />
        ))}
        <text x={left} y={height - 5}>
          0 s
        </text>
        <text x={width - right} y={height - 5} textAnchor="end">
          {replay.duration_s} s
        </text>
      </svg>
      <p>
        <span className="queue-key afterlight">AFTERLIGHT</span>
        <span className="queue-key baseline">Ordinary baseline</span>
      </p>
      <small>
        Queue totals alone are not the benchmark recovery metric. Recovery
        compares excess queue area against baseline in the predeclared window.
      </small>
    </figure>
  );
});
