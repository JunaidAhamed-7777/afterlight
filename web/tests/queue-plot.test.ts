import test from "node:test";
import assert from "node:assert/strict";
import type { QueuePoint } from "../src/queueTypes.ts";
import { liveQueueWorld, queueCutoff, queueScale, revealedQueue } from "../src/queuePlot.ts";

// Synthetic graph mechanics only; these counts are never published as traffic evidence.
const points: QueuePoint[] = [{ t: 0, queue_count: 0 }, { t: .5, queue_count: 3 },
  { t: 1, queue_count: 99 }, { t: 1.5, queue_count: 1 }, { t: 2, queue_count: 10 }];

test("playback reveals only actual samples at or before its absolute clock", () => {
  assert.deepEqual(revealedQueue(points, -.1), []);
  assert.deepEqual(revealedQueue(points, 0), points.slice(0, 1));
  assert.deepEqual(revealedQueue(points, .75), points.slice(0, 2));
  assert.deepEqual(revealedQueue(points, 1), points.slice(0, 3));
  assert.deepEqual(revealedQueue(points, 100), points);
});

test("rewinding removes later samples and never retains a previous future peak", () => {
  assert.deepEqual(revealedQueue(points, 2), points);
  const rewound = revealedQueue(points, .5);
  assert.deepEqual(rewound, points.slice(0, 2));
  assert.equal(rewound.some((point) => point.queue_count === 99), false);
});

test("all revealed extrema and endpoints survive without averaging, smoothing or decimation", () => {
  const before = JSON.stringify(points);
  const dense = Array.from({ length: 1801 }, (_, i) => ({ t: i / 2, queue_count: i % 2 ? 161 : 0 }));
  assert.deepEqual(revealedQueue(dense, 900), dense);
  assert.equal(revealedQueue(points, 1.75).at(-1), points[3]);
  assert.equal(revealedQueue(points, 2)[2], points[2]);
  assert.equal(JSON.stringify(points), before);
});

test("time is clamped to the recording window and unavailable time reveals no future", () => {
  assert.equal(queueCutoff(-5, 900), 0);
  assert.equal(queueCutoff(990, 900), 900);
  assert.equal(queueCutoff(182.25, 900), 182.25);
  for (const invalid of [NaN, Infinity, -Infinity]) assert.equal(queueCutoff(invalid, 900), 0);
});

test("shared queue scale has integer ticks and preserves the largest real count", () => {
  for (const peak of [0, 1, 3, 8, 99, 162, 251, 1000]) {
    const result = queueScale({ afterlight: [{ t: 0, queue_count: peak }], baseline: [] });
    assert.ok(result.maximum >= peak && result.maximum > 0);
    assert.equal(result.ticks[0], 0);
    assert.equal(result.ticks.at(-1), result.maximum);
    assert.ok(result.ticks.every(Number.isInteger));
    assert.ok(result.ticks.length >= 4 && result.ticks.length <= 6);
  }
  assert.deepEqual(queueScale({ afterlight: points, baseline: [{ t: 0, queue_count: 162 }] }), { maximum: 200, ticks: [0, 50, 100, 150, 200] });
});

test("live display uses ordinary until genuine Afterlight samples have arrived", () => {
  assert.equal(liveQueueWorld({ afterlight: [], baseline: [] }), "baseline");
  assert.equal(liveQueueWorld({ afterlight: [], baseline: points }), "baseline");
  assert.equal(liveQueueWorld({ afterlight: [points[0]], baseline: points }), "afterlight");
});
