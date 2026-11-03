import { loadRecordingDirect, type PublishedEntry } from "./recordingCore.ts";

const scope = self as unknown as {
  onmessage:
    | ((
        event: MessageEvent<{
          entry: PublishedEntry | null;
          url: string;
          expectedSha256?: string;
        decodedLimit?: number;
        }>,
      ) => void)
    | null;
  postMessage: (value: unknown) => void;
};
scope.onmessage = async (event) => {
  try {
    const replay = await loadRecordingDirect(
      event.data.entry,
      event.data.url,
      new AbortController().signal,
      event.data.expectedSha256,
      event.data.decodedLimit,
    );
    scope.postMessage({ type: "loaded", replay });
  } catch (error) {
    scope.postMessage({
      type: "error",
      message:
        error instanceof Error
          ? error.message
          : "The recording could not be prepared.",
    });
  }
};
