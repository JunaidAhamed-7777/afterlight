# Omen acceptance log

Only actual execution reported by the designated Omen tester belongs here.
Source compilation and cloud review are not acceptance tests. No benchmark or
held-out dataset has yet been evaluated.

## 2026-11-02, first local checks (reported 21:28 UTC)

Environment: Windows x64, PowerShell 7.6.5, Python 3.12.15 venv,
Node 26.8.1/npm 12.2.1. Earlier headed Chrome 156 WebGL2 capability/readback check
passed with no GL error; this does **not** establish product rendering performance.

- Across source checkpoints `4068e3f` and `06ae7b1`, the tester reported 25 requested
  unit tests passing. This is not a pass for later source revisions or all flows.
- Actual HTTP adversarial checks at `4068e3f` found an incomplete two-field replay
  accepted as HTTP200, and nonfinite JSON causing an uncaught response failure.
  Source fixes were published in `7ea95f4` (nonfinite JSON) and `a3f9106` (canonical
  full replay validation). Local regression recheck is pending.
- Both fixture and full-city netconvert commands at `06ae7b1` failed because the
  executable was not discovered. XML inputs exist; **no SUMO network or real
  traffic rollout passed**. Packaged executable discovery is being corrected.
- Synthetic edge probes found finite inputs could overflow objective/recovery
  outputs and identical demand hashes could be split under different group IDs.
  Defensive fixes and regressions are in progress. No real dataset was evaluated.

Raw local logs remain with the tester. This narrative is a scoped summary, not a
replacement for exact command logs, generated evidence or future reruns.

## 2026-11-02, `a3f9106` cohort (reported 21:46 UTC)

- **Passed:** 66 Python tests, 16 frontend unit tests and all three requested HTTP
  regressions, as reported by the Omen tester. These results are scoped to this
  source cohort, not later commits.
- **Blocked:** `npm ci` exited 1 with `EIDLETIMEOUT` reaching the official npm
  registry; cleanup also reported `EPERM` on `node_modules`. The incomplete
  install left TypeScript unavailable, so production build and product browser
  rendering were not validated.
- GitHub fetch remained responsive; a direct official dependency download was
  very slow. An isolated, exact-lock, Windows x64 offline npm cache is being
  prepared as a transfer artifact, not a Linux `node_modules` substitute.
- No successful SUMO network conversion or traffic rollout has been reported in
  this cohort summary. The next pinned cohort is `fdf251d`; it must provide its
  own results and artifacts. No pilot or held-out study has been run.

## 2026-11-02, `fdf251d` cohort (reported 21:49 UTC)

- **Passed:** 95 Python tests (API21 / simulation41 / evaluation33), 22 frontend
  unit tests and six original regression probes, as reported by the Omen tester.
- **Dependency diagnosis:** Eclipse SUMO, TraCI and sumolib are absent because
  their downloads did not complete. There is still no successful SUMO conversion,
  paired run, real replay, generation job, pilot or held-out evaluation.
- Dependency installation did not complete. Existing installation outcomes must
  be checked before restarting installation; application acceptance is pending.
- Official, lock-integrity-verified Windows dependency transfer artifacts are
  being prepared separately from application source. No tests or simulations
  were moved to the cloud.

## 2026-11-02, `1312e865` cohort (reported 23:25 UTC)

- **Passed:** 119 Python tests (API25 / simulation55 / evaluation39); one optional
  synthetic ML test was skipped because its explicit opt-in and scikit-learn
  prerequisites were not provided. Evaluation completed after an earlier tooling
  interruption; the interruption itself was not a test failure.
- **Frontend:** 44 tests passed; one failed with `ERR_MODULE_NOT_FOUND` for Three
  because the dependency installation remains incomplete. This is not a complete
  frontend pass. No product browser rendering or frame-time result exists yet.
- No SUMO conversion, paired run, real replay, pilot, or held-out study ran.
- Source-bound compiled application previews are being prepared to allow browser
  QA independently of npm installation. They do not satisfy source-install/build
  reproducibility or simulator acceptance gates. Browser test harnesses also need
  the same safe default-flag exclusions used in the earlier capability check.

## 2026-11-02, `ce29330` preview checkout (reported 23:55 UTC)

- Exact-byte preview verification correctly stopped on a Windows CRLF mismatch;
  preview unit checks reported three passed and one manifest error. The application
  server and browser run did not proceed through a failed provenance gate.
- The tester isolated 38 text mismatches (25 source, 12 output, canonical map JSON).
  Every one matched the manifest after diagnostic CRLF-to-LF comparison; all ten
  binary runtime assets matched their exact hashes. Checkout was clean with the
  existing user-level `core.autocrlf=true` setting.
- Both headed harnesses were inspected with sandbox enabled and all seven required
  default-argument exclusions. This is harness inspection, not browser acceptance.
- `b61bd9b` adds repository-scoped LF attributes and a targeted clean-input refresh;
  the exact-byte manifest gate remains unchanged. Its actual Windows rerun is
  pending. No global Git configuration change or simulation run is implied.

## 2026-11-03, `b61bd9b` preview refresh (reported 00:08 UTC)

- The targeted Git checkout command returned success but left all 38 CRLF text
  inputs unchanged. Exact manifest verification failed again; preview checks were
  three passed and one error. No server/browser run was accepted.
- This exposed an incorrect helper assumption, not a hash-gate failure: a clean
  checkout can be skipped by `checkout-index` even when force is requested.
- `3f679de` replaces that mechanism with hash-verified indexed-byte extraction and
  guarded atomic replacement, followed by exact file hashes and content-clean
  postconditions. Its five mocked guards are authored; actual Omen execution of
  the new helper and product browser acceptance remain pending.

## 2026-11-03, `3f679def` first application acceptance (reported 00:30 UTC)

Compiled application source: `1312e865`; preview/harness/refresh source: `3f679def`.

- **Passed:** all 48 exact raw-byte manifest inputs, all nine preview tests,
  and all 11 headed Chrome application smoke checks (5.59 s test elapsed), with
  no uncaught page errors. Actual WebGL2 rendered on the Omen AMD integrated GPU.
- **Passed:** synthetic local-generation protocol UI checks (3.90 s test elapsed).
  These intercepted API responses tested UI request recovery, not a real job,
  traffic run, or measured improvement.
- **Visual findings:** city overview was horizontally cropped on mobile and the
  taller local-generation layout; favicon request returned 404. Responsive fit
  and favicon corrections are being authored and require a new browser cohort.
- Index and content diffs were empty, but Git status retained stale stat metadata
  for 38 refreshed paths. A scoped metadata-refresh diagnostic is separate from
  the successful byte checks; no reset or global configuration change is implied.
- Real paired playback, ghost timing against SUMO, loaded-traffic performance,
  actual simulation and ML evaluation remain untested. Smoke elapsed times above
  are test-run durations, not renderer frame-time or traffic-performance metrics.

## 2026-11-03, `ba0c38a` recovered local cohort (reported 03:59 UTC)

- Both owner-downloaded offline bundles matched their expected hashes. The local
  install completed for all four SUMO packages at 1.28.0 and the locked npm
  dependencies. Frontend production compilation succeeded on Omen.
- **Reported unit results:** 262 Python passed / four skipped; 54 frontend Node
  tests passed. The focused source-identity run separately reported 19 passed /
  two platform-specific skips. Do not add these focused counts to the aggregate.
- Synthetic local-generation protocol checks passed, including responsive views.
  The headed browser run passed 12 checks, then failed a harness focus assertion:
  Reset → Tab correctly entered the keyboard-focusable map, and the next Tab left
  it. The harness is being corrected to accept and verify that intended sequence.
- A real three-junction paired fixture ran. Its ordinary baseline is **invalid**
  because a collision was reported at 153.00 s (captured at the next 153.5 s
  sampling boundary). Both worlds completed 120 civilian vehicles, but completion
  does not override the collision or make this a valid comparison. No replay or
  benchmark gain may be promoted from this pair.
- The colliding vehicles were a turning car (`civilian_00067`, 4.4 m) and a truck
  (`civilian_00094`, 7.2 m) inserted at the start of outgoing edge `J3_J2` at
  152.5 s. Both had numeric `departPos=0`. SUMO positions refer to the front
  bumper; the observed truck rear extended into the junction. This supports an
  unsafe insertion-position diagnosis, but a fresh controlled rerun must confirm
  the correction. Existing invalid evidence remains retained, not relabeled.
- Full-city conversion completed with six no-incoming-lane warnings and four
  intersecting-left-turn warnings. These require lane-level connection review;
  no city rollout, pilot, training, or held-out evaluation has passed.
- A separate isolated local checkout was used after Git's stale metadata blocked
  a normal fast-forward. Existing checkout contents were preserved. This is not
  evidence that the stale-stat metadata issue itself was repaired.

The enhanced 3D city/camera revision `14ea738` and compiled preview `63b7874` are
later work and are **not covered** by these results. Their new asset, cutaway and
camera tests still require a pinned Omen run.
