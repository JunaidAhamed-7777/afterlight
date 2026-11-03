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
