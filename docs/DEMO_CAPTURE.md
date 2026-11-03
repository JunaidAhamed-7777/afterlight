# Desktop demo capture

Capture the final video **after the Canva identity is in the frontend**. The
default command makes a short unpublished capability check; it does not run the
full walkthrough or publish media.

The harness uses installed Chrome, project-pinned Playwright, and installed
FFmpeg/ffprobe. It records the browser viewport at 1280×720 and 25 fps, with a 1:1
pixel size. `--width 1600` selects 1600×900 instead. Keep other browser/GPU work
idle during capture.

```powershell
.\.venv\Scripts\python.exe web/tests/capture_desktop_demo.py `
  --base-url http://127.0.0.1:5198/ `
  --output local-runtime/demo-capability-01
```

For the final, use the actual post-identity deployment URL and explicit mode:

```powershell
.\.venv\Scripts\python.exe web/tests/capture_desktop_demo.py `
  --mode final `
  --base-url https://YOUR-VERIFIED-DEPLOYMENT.vercel.app/ `
  --study-manifest-sha256 $releasedManifestSha `
  --output local-runtime/final-desktop-demo-01
```

`--build-manifest` optionally verifies an exact isolated build inventory before
and after recording. The catalog and both original decoded replay checksums are
always verified. Every invocation needs a fresh output directory.

Set `$releasedManifestSha` to the exact manifest hash from the completed audited
public Study release. Final mode independently verifies that real public pack
and every physical companion under its 4 MiB bound before opening the browser.
Lossless reproduction grids have explicit 128 MiB decoded/decoder-memory caps.
It rejects
unpublished, incomplete, mismatched or invalid evidence. There is no positive
fixture or placeholder fallback. Default dry-run mode never fetches Study data.

## Walkthrough

The 70-second sequence starts after the genuine initial recording is ready.
Actual initial loading is retained in the video, so the final duration should be
roughly 70–85 seconds. The harness rejects a final video outside 60–90 seconds.

1. **0–8s:** Full-city view of the Cross-city recording at 2×. Both hospitals and
   the expanded street grid remain part of the real scene.
2. **8–24s:** Follow Ambulance and watch the Afterlight response. The native
   Recorded label, clock, speed and playback controls stay visible.
3. **24–28s:** Pause and seek to a genuine comparison moment.
4. **28–36s:** Switch to Ordinary and follow its ambulance in its own traffic
   world.
5. **36–48s:** Follow Ghost in the Afterlight scene, inspect ghost visibility in
   Settings, then restore it with the actual Follow Ghost control.
6. **48–62s:** Open the Westhaven recording, seek within its actual ambulance
   journey, and follow the response to the other hospital. Real loading remains
   visible.
7. **62–67s:** Pause and inspect This run, civilian delay and vehicle accounting
   in the independently scrolling sidebar.
8. **67–70s:** Open Study and show only the actual released report. Its native
   HTTP 200 responses, checksums, episode counts and comparison count must match
   the independently verified publication. The ready report remains visible
   for at least 2.5 seconds even if its real loading takes longer.

Action times, real recording IDs, hashes, playback times and speed settings are
saved in `report.json`. This is a returning-user walkthrough: only the completed
tour preference is seeded. No trace, signal, metric or simulation request is
substituted, and no new simulation job is submitted.

## Review and publish

The output includes native WebM, silent H.264 MP4, real PNG screenshots at the
storyboard milestones, an encoding log, and the capture report. Compression uses
two passes at the native resolution and 25 fps. It adds no music, voiceover,
overlays, interpolated frames or speed changes. Only a verified empty
`about:blank` prefix from the native recorder is omitted; actual product loading
and every subsequent pause remain intact. Playback speed changes are made using
the visible product control.

Inspect the MP4 and milestone screenshots before publishing. Check that WebGL
content is visible, control labels remain readable, world/ghost changes are
clear, the destination changes to Westhaven, and the Results match the chosen
recording. Use post-identity milestone PNGs for the README only after this review.

The MP4 must be at most 8,000,000 bytes. With an exact build manifest, final mode
also rejects a combined build-and-video size of 50,000,000 bytes or more. The
harness never copies media into public assets or deploys it; publishing remains
a separate release step.
