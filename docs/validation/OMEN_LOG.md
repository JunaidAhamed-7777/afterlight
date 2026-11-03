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

## 2026-11-03, `63b7874` enhanced desktop city (reported 04:27 UTC)

Compiled application source: `14ea738`. Actual Omen checks reported:

- All 56 exact manifest hashes matched; enhanced asset structure tests **8/8**,
  locked npm production build succeeded, frontend Node tests **57 passed**.
- Headed desktop browser checks **13/13** and synthetic local-generation protocol
  checks passed. No shader, browser console or uncaught page error was reported.
- Actual perspective geometry, X/Y/Z rotation including roll, pan and zoom were
  visually inspected. One foreground building out of 187 became transparent;
  toggling the option restored it. This was a real renderer observation, not a
  simulated traffic outcome.
- Reported renderer counters were 19 draw calls and 78,564 triangles. Sampled
  requestAnimationFrame intervals were median 6.10 ms, p95 6.30 ms, maximum
  18.8 ms. These are scheduling intervals, **not GPU timings, loaded-traffic FPS,
  or a whole-product performance benchmark**.
- Preview unit checks were eight passed / one failed because a test hardcoded an
  obsolete compiled-source SHA. Exact hash verification itself passed. The test
  is being corrected to read the manifest's declared source rather than freeze
  a historical build forever.
- The camera panel visibly covered the journey/map-inspection label. The later
  `b951090` preview moves that label into its own row and requires an overlap
  regression; this acceptance does not validate that later fix.
- A supplemental whole-camera-state comparison failed after a 10 px viewport
  width change although its physical camera fields were identical. Viewport
  metadata must be checked against actual layout separately from physical pose;
  it is not evidence that a transparency toggle moved the camera.

No new valid SUMO pair or collision-fix acceptance was reported with this UI
cohort. Desktop-only acceptance is the current target; mobile work is excluded.

## 2026-11-03, `7ef8ffe` desktop and network conversion (reported 04:41 UTC)

Compiled application source remains `f54dc39`, from preview `b951090`.

- Preview checks **9/9**, enhanced asset checks **8/8**, locked npm production
  build and frontend Node checks **57/57** passed.
- Headed desktop browser checks **14/14** and synthetic local-generation protocol
  checks passed. No additional mouse/cutaway supplemental probe ran in this cohort.
- Three-junction fixture and full-city network conversion both exited zero with
  empty warning logs. This resolves the previously observed conversion warnings
  for this checkpoint, not traffic safety or paired-run acceptance.
- No new fixture pair, ordinary-controller negative control, or city traffic run
  completed in this reported cohort. The earlier invalid collision evidence is
  unchanged; the insertion correction still needs a fresh real run.
- The focused/full Python batch launch lost its transport response during laptop
  shutdown. Its outcome is **unknown**, not passed or failed. Inspect the saved
  `python-gates` records and actual process state before starting another batch.
  A network qualification script write was also uncertain and it was not run.
- The newer preview was not promoted to the user-facing localhost port before
  shutdown. No training, pilot or held-out evaluation result is claimed.

Subsequent source changes are not covered by this acceptance.

## 2026-11-03, `f34ab49` first refreshed gate (reported 06:29 UTC)

- Strict preview verification and offline production build passed.
- Simulation unit checks: **197 passed, 1 failed, 2 Windows-specific skips**.
  The failing synthetic recovery test expected the legal-boundary message, but
  its early mutation crossed the release itself and correctly hit the earlier
  preceding-release guard. The audit was not weakened. The correction uses an
  early passage release to isolate minimum-green timing, and adds an explicit
  recovery-before-existing-release regression. The corrected tests are pending
  a fresh Omen run.
- The gate stopped: evaluation/API/asset/frontend Node/network/browser/traffic
  acceptance was not reached in this cohort. No active child/test remained at
  the reported checkpoint. No new real paired-run or ML result is claimed.

The next source cohort must rerun the affected gate; build success does not turn
the failed unit checkpoint into a pass.

## 2026-11-03, `2c03d5a` recovery fixture accepted; next gate (reported 06:39 UTC)

- Focused recovery audit checks **19/19 passed**.
- Simulation checks **199 passed, 2 Windows-specific skips**.
- Evaluation checks **183 passed, 3 errors, 2 skips**. All three errors came
  from the shared synthetic `test_pilot_runtime_guards.py` priority fixture:
  it released at 55 s but supplied no recovery sequence through its 100 s end.
  The stricter audit correctly rejected this incomplete fixture. The fixture
  correction supplies legal recovery/ordinary transitions and explicit
  endpoint mutations; the audit itself remains unchanged. Omen rerun is pending.
- Later acceptance gates stayed held. This result does not establish API,
  frontend, current geometry, browser, network or traffic acceptance for this
  checkpoint. No new real pair, pilot, model or held-out result is claimed.

## 2026-11-03, `38ae571` runtime fixtures accepted; API depth failure (reported 06:51 UTC)

- Focused pilot-runtime checks **19/19 passed**; strict preview verification and
  offline production build passed.
- Simulation checks **199 passed, 2 skips**; evaluation checks **186 passed,
  2 skips**.
- API checks **41 passed, 4 failed**. The interpreter accepted 2,000 nested
  JSON arrays without raising `RecursionError`, exposing a real missing explicit
  depth bound in the API. This is not a traffic outcome or a test expectation to
  relax. The correction adds deterministic bounded JSON handling at the API
  boundaries, with fresh Omen acceptance required.
- The remaining six journal stages, browser acceptance and traffic were not run
  in this cohort. No real paired-run, pilot, model or held-out result is claimed.

## 2026-11-03, independent `38ae571` checks and focused `f4b665d` API (reported 07:02 UTC)

- Independent checks on `38ae571` passed: **64 Python checks, 79 frontend Node
  checks and four desktop suites**. These were separate scoped checks, not a
  successful full journal or traffic qualification. Detailed suite attribution
  remains to be reconciled from the local reports.
- Focused API on `f4b665d`: **49 passed, 1 error**. The original four depth
  failures and five new boundary checks passed. The remaining error exposed a
  contextual byte-cap regression: a persisted job record's explicit 1 MiB
  reader cap was incorrectly replaced during parsing by the replay cap lowered
  to 100 bytes in the regression test. The fix threads the explicit context cap
  through both stages without relaxing depth, UTF-8 or finite-number checks.
- No full `f4b665d` journal or traffic run started. A fresh pinned cohort is
  required; no new paired-run/pilot/model result is claimed.

## 2026-11-03, `11be524` complete units/desktop and fixture qualification (reported 07:21 UTC)

Compiled preview source: `b2a5e60`, artifact checkpoint `99083b2`.

- Full unit/network journal: **500 Python checks passed, four skipped; Node
  85/85 passed** (585 passing checks in total). All nine source checks stayed
  pinned. Both network conversions exited zero with empty warning logs.
- All four desktop suites passed. Static network qualification passed **33/33**,
  including all 200 city pickup/hospital routes. The focused V3 probe passed
  pointer controls, selective building fading and unobscured journey text at
  1440×1000 and 1280×720. This is desktop, not mobile acceptance.
- Fixed-priority fixture and ordinary/ordinary negative-control pairs qualified.
  Each world completed all **120 scheduled civilians**, with zero running or
  uninserted vehicles, collisions or teleports. Exact negative-control trace and
  controller equality passed. These are correctness qualifications, not a
  policy-benefit benchmark or proof across all routes/traffic regimes.
- The sparse-city pair was running when Omen transport disconnected. Its process
  and traffic-journal outcome are **unknown**. No retry or cancellation was made.
  Inspect the existing process and saved journal before any new attempt.
- Actual city replay/ghost alignment and a real local-generation API job remain
  unaccepted. No pilot, training or held-out evaluation was performed; the
  public recording catalog remains empty.

The original invalid fixture evidence is retained. The later qualified case
does not erase that failure or turn source-only revisions into measured gains.


## 2026-11-03, `11be524` traffic journal resolved (reported 07:35 UTC)

The previous transport-gap entry is historical: the existing saved journal was
inspected rather than treating disconnection as termination or blindly rerunning.
All **nine traffic stages exited zero**, source fingerprints matched, and no
active process remained. Total journal wall time was **94.98 s**; this is a
qualification-run duration, not a benchmark or rendering performance measure.

- Fixed fixture and ordinary/ordinary fixture pairs completed **120/120 civilians
  in each world**. Sparse-city P001 → HOSP_EAST completed **37/37 in each world**.
- Across all six worlds at 600 s: zero collisions, teleports, running civilians
  and uninserted civilians. City counts at 240 s still included **21 and 20 running**;
  do not substitute the earlier horizon for the common completed drain.
- Signal/recovery, automated alignment, demand/tripinfo and causality audits
  passed. The prior exact ordinary-controller negative control remains qualified.
- City ambulance journeys: **210.5 s baseline, 182.5 s priority**. This is one
  exploratory qualification pair, not aggregate benefit, learned improvement,
  evidence across regimes, or a traffic-safety claim. Qualification seed 7 stays
  excluded from scientific study data.
- Actual rendered city replay/ghost alignment and a real local-generation API job
  remain pending. No pilot, model training or held-out evaluation ran, and the
  public recording catalog remains empty. Preserve all earlier invalid evidence.

## 2026-11-03, `5293ae0` real city viewing checkpoint (reported 08:02 UTC)

- 64 Python checks, 89 Node checks and the local production build passed.
  This is a scoped follow-up, not a replacement for the full `11be524` journal.
- The new real-replay harness stopped before playback: its direct recording
  selection was disabled because the default journey went to Westhaven while
  the genuine recording went to HOSP_EAST (Eastbank). The product's normal **Open available
  recording** action selected the correct route. Harness-only fix `5dad4cb`
  uses that action and still asserts the exact recorded identity; rerun pending.
- A separate normal-UI inspection of the retained `11be524` city pair at absolute
  times 205, 207 and 220 seconds passed solid/ghost matrix and world-switching
  isolation checks. No browser errors or external requests were observed.
  Road placement and turn direction looked correct in those views. Fractional
  interpolation was not exercised; this is not the full automated visual gate.
- Geometry inspection found approximately 5 cm of tyre penetration across
  48 contacts. Precise vertical placement and stop-line alignment remain open.
  A geometry-grounding correction and numerical contact regressions are being
  prepared; no corrected result has been measured yet.
- The evidence copy matched all 109 original files (29,283,211 bytes), including
  hashes, sizes and modification times, when copied. The final original-file
  comparison did not execute because the approval review could not complete;
  do not silently promote the earlier comparison into an end-of-test guarantee.
- No demo promotion, simulator rerun, pilot, training or held-out evaluation
  occurred in this checkpoint. Original failed harness evidence is retained.


## 2026-11-03, `3060716` corrected genuine replay and preservation (reported 08:40 UTC)

Corrected preview compiled source: `975dd29`. This is scoped acceptance, not a
new full unit/network/traffic cohort or a policy experiment.

- **37 Python and 90 Node checks passed**. The genuine replay harness passed at
  absolute times **61, 61.5 and 242 s**, including fractional playback and actual
  solid/ghost matrices and world-switch isolation. The earlier separate manual
  checks at 205, 207 and 220 s remain distinct evidence. No browser errors arose.
- The measured lowest tyre contact was **0.180000007 m**, matching the authored
  road height. Twelve screenshots supported good gross road placement. This
  does **not** certify exact stop-line or sub-centimetre visual alignment.
- The previously incomplete preservation check now passed: both evidence copies
  matched all **109 original files**; **243 tracked files**, source HEAD and index
  were unchanged. This closes the earlier approval/transport-related comparison
  gap without deleting its historical record.
- The existing read-only `5293ae0` demo on ports **5180/8765** was untouched;
  corrected `3060716` staging used **5181**. No demo promotion or simulator rerun
  occurred. HOSP_EAST is Eastbank; the earlier prose name Eastgate was corrected,
  with no change to the recording's stable hospital ID.
- No ML dependencies were installed. A real local-generation API lifecycle,
  pilot throughput/action diversity, training and held-out evaluation remain
  pending. These rendering checks do not establish model or policy benefit.
