import type { Replay } from "./types.ts";
import { loadRecordingDirect, type PublishedEntry } from "./recordingCore.ts";
export { bindRecording, recordingBytes } from "./recordingCore.ts";

/** Prepare dense real traces away from the render/input thread. */
export async function loadRecording(entry: PublishedEntry | null, url: string, signal: AbortSignal): Promise<Replay> {
  if (typeof Worker === "undefined") return loadRecordingDirect(entry, url, signal);
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./recording.worker.ts", import.meta.url), { type: "module" });
    let settled = false;
    const cleanup = () => { signal.removeEventListener("abort", abort); worker.terminate(); };
    const fail = (error: Error) => { if (settled) return; settled = true; cleanup(); reject(error); };
    const abort = () => fail(new DOMException("Recording loading was canceled.", "AbortError"));
    worker.onmessage = (event: MessageEvent<{ type: string; replay?: Replay; message?: string }>) => {
      if (settled) return;
      if (event.data.type === "loaded" && event.data.replay) {
        settled = true; cleanup(); resolve(event.data.replay);
      } else fail(new Error(event.data.message ?? "The recording could not be prepared. Retry the recording."));
    };
    worker.onerror = event => {
      event.preventDefault();
      fail(new Error("The recording worker could not start. Reload the viewer and retry."));
    };
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) { abort(); return; }
    worker.postMessage({ entry, url });
  });
}
