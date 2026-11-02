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
