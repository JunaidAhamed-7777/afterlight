export interface QueuePoint {
  t: number;
  queue_count: number;
}

export interface QueueSeries {
  afterlight: QueuePoint[];
  baseline: QueuePoint[];
}

export type QueueWorld = keyof QueueSeries;
