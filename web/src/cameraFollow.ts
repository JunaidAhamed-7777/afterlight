import type { Frame, Vehicle } from "./types.ts";
import { interpolatedFrame, vehiclePose } from "./replay.ts";
/** Camera-only index. No added vehicle, pose, time shift or simulation mutation. */
export class AmbulanceCameraTrack {
  readonly frames: Frame[];
  private samples: Array<{ t: number; vehicle: Vehicle }>;
  private poseFrames: Frame[];
  constructor(frames: Frame[]) {
    this.frames = frames;
    this.samples = [];
    this.poseFrames = frames.map(frame => {
      const vehicle = frame.vehicles.find(v => v.id === "ambulance");
      if (vehicle) this.samples.push({ t: frame.t, vehicle });
      return { t: frame.t, vehicles: vehicle ? [vehicle] : [], signals: [], queue_count: 0 };
    });
  }
  target(time: number): [number, number, number] | null {
    if (!Number.isFinite(time) || !this.samples.length) return null;
    const first = this.samples[0], last = this.samples[this.samples.length - 1];
    let vehicle: Vehicle;
    if (time <= first.t) vehicle = first.vehicle;
    else if (time >= last.t) vehicle = last.vehicle;
    else {
      const live = interpolatedFrame(this.poseFrames, time)?.vehicles.find(v => v.id === "ambulance");
      if (live) vehicle = live;
      else {
        // A missing sample is not invented motion: retain the last observed pose.
        let low = 0, high = this.samples.length - 1;
        while (low < high) {
          const mid = Math.ceil((low + high) / 2);
          if (this.samples[mid].t <= time) low = mid; else high = mid - 1;
        }
        vehicle = this.samples[low].vehicle;
      }
    }
    const [x, elevation, z] = vehiclePose(vehicle);
    return [x, elevation + 1.5, z];
  }
}
/** Scrubbing/replay changes must not fly across the city through stale positions. */
export function cameraSeek(previous: number | null, next: number, elapsed: number): boolean {
  return previous !== null && (next < previous || next - previous > Math.max(1, elapsed * 10));
}
export function followBlend(elapsed: number, playing = true): number {
  // A paused recording has one exact target. Finish the camera translation
  // immediately so close-up inspection cannot drift between still frames.
  if (!playing) return 1;
  return 1 - Math.exp(-Math.max(0, Math.min(.1, elapsed)) / .09);
}
export const MAX_CAMERA_ZOOM = 48;
