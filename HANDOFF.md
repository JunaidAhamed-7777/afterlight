# AFTERLIGHT — local handoff

**Frozen at the owner's request on November 3, 2026, 08:47 UTC / 14:17 IST.**
The owner will continue on their device. Cloud development, delegated work,
new builds, tests, simulations and dependency preparation have stopped. The
final publication preserves the work already written; it is not a claim that
all of it is validated.

## Start here: source and preview are different checkpoints

| Item | Exact checkpoint / status |
|---|---|
| Final frozen source | The commit containing this handoff; obtain its full SHA with `git rev-parse HEAD`. Latest desktop redesign is included but **unbuilt and untested**. |
| Last accepted corrected viewer | `3060716ef623a60801b3a94aa9c0824e0511a949` |
| Source compiled into that preview | `975dd295a7f3ca06e42b814c616b77108b6fced7` |
| Genuine recorded simulation source | `11be52480661523e56bed3d4a1d2f572c242e372` |
| Earlier user-visible demo | `5293ae034e10b82a4d589a9bf434c243201d60b4`, compiled from `92cc07dc1efb98a13e5ae843308f6ab3d7968e7d`; predates corrected tyre height. |

**Important:** the committed `preview/` was deliberately not rebuilt after the
halt. Its manifest still binds the previously accepted source above. On the
final source checkout, `scripts/serve_preview.py --verify-only` should refuse
changed frontend inputs. Do not disable that guard, normalize hashes, or label
the older artifact as the new layout. Use a separate checkout at `3060716` for
the accepted preview, or build and validate the new source locally before
refreshing and committing a new preview with `scripts/build_preview.py`.

All currently authored project source, tests and documentation are included in
the final publication. No known project-source changes are intentionally left
uncommitted. Ignored dependencies, build caches, private raw experiment files
and incomplete dependency-download staging are not public source and were not
uploaded. The final remote SHA and clean-worktree verification are reported
separately by the publisher because this document cannot embed its own commit.

## Latest UI work included, not yet accepted

The owner requested a less confusing desktop workspace. The frozen changes are:

- A viewport-bound desktop shell: settings, evidence and footer scroll on the
  **left**, while the 3D city and playback remain visible on the **right**.
- A named, keyboard-focusable left scroll region, stable visible scrollbar,
  compact header and in-flow camera dock instead of controls over the city.
- Explicit zoom buttons and a larger close-zoom range (maximum 48); perspective
  near plane reduced to 0.1 m. Existing building cutaway remains.
- Camera-follow translation preserves zoom, orbit and roll. Deliberate panning
  or overview/explore releases follow; ordinary orbit and zoom do not. Tracking
  uses the AFTERLIGHT ambulance in both world views, with camera-only endpoint
  holding and discontinuity handling for seeking/replay changes.
- Higher-contrast, screen-size-responsive controlled-link arrows, batched into
  instanced foreground/backing layers. These are individual movement states,
  not a universal green/red junction indicator.

Affected source: `web/src/App.tsx`, `CameraControls.tsx`, `CityView.tsx`,
`GeometryLayer.ts`, new `cameraFollow.ts`, `web/src/styles/app.css`, and
`DESIGN.md`. New authored checks: `camera-follow.test.ts`,
`signal-presentation.test.ts`, and `desktop_layout_checks.py`.

Static review occurred, but **no compilation, unit tests, screenshots or real
replay acceptance were executed for this final desktop redesign**. In
particular, its hierarchy, follow feel, close zoom, symbol overlap, clipping,
layout at 1280×720 and 1440×900, and loaded-traffic performance still need local
review. Do not inherit the older viewer's results automatically.

## What actually passed on Omen

See [the chronological evidence log](docs/validation/OMEN_LOG.md) for failures
and precise scope. Do not add these overlapping counts together.

- `11be524`: 500 Python checks passed, four skipped; 85 Node checks passed; both
  network conversions warning-free; four desktop suites passed; static network
  qualification 33/33, including all 200 pickup/hospital routes.
- The fixed-priority fixture, ordinary/ordinary negative control and sparse-city
  P001 → HOSP_EAST pairs qualified. Each fixture world completed 120 civilians;
  each city world completed 37. All six worlds had no collisions, teleports,
  running or uninserted vehicles by the common 600 s drain endpoint. Ordinary
  negative-control trace/control equality passed. Signal/recovery, demand,
  lifecycle/tripinfo, geometry and causality audits passed.
- The city pair still had 21/20 civilians running at 240 s; all drained by 600 s.
  Its ambulance journeys were 210.5 s ordinary versus 182.5 s fixed priority.
  This is **one exploratory qualification pair**, not aggregate benefit, learned
  performance, a safety claim or a held-out result.
- `5293ae0`: 64 scoped Python and 89 Node checks plus local production build
  passed. The first real-replay harness failed because it selected a disabled,
  journey-filtered dropdown; the route-aware entry fix is retained. Separate
  real-view checks at 205/207/220 s passed world/ghost matrix isolation. About
  5 cm tyre penetration was found, not hidden.
- `3060716`: 37 scoped Python and 90 Node checks passed. Genuine replay checks at
  61/61.5/242 s passed, including fractional time, active/baseline inspection,
  ghost isolation and actual rendered matrices. Lowest tyre geometry measured
  0.180000007 m against the authored 0.18 m road surface. No browser errors.
  Twelve screenshots showed good gross road placement; exact stop-line and
  sub-centimetre visual contact are **not certified**.
- Final preservation retry passed for both retained 109-file evidence copies;
  243 tracked files and source HEAD/index were unchanged. The earlier temporary
  approval-review failure remains documented, but preservation uncertainty was
  subsequently resolved.

No controlled multi-regime pilot, study collection, fitted model, held-out
comparison, actual generation-API lifecycle acceptance or genuine saved-job UI
recovery acceptance has been completed. The public recording catalog remains
empty. The working user demo uses a private audited local catalog, not fake or
newly generated traffic.

## Preserve the live local demo and raw evidence

Last reported local services (check process/port state before acting):

- `http://127.0.0.1:5180/local.html`: the user's ordinary Chrome demo, older
  `5293ae0` viewer, genuine 6,951,751-byte replay. No request interception is
  needed for this demo. Its API on port 8765 is **read-only**.
- Port 5181: corrected `3060716` staging viewer; do not assume its ordinary
  browser catalog contains the isolated test recording.

Do not stop, replace or pull source underneath these services while the owner
uses them. Do not launch generation on an occupied read-only API port. A lost
connection never proves a simulator, fetch or installer ended: inspect actual
process state and existing journals before retrying.

Keep the original complete `traffic/fixture-fixed`, `traffic/fixture-ordinary`
and `traffic/city-sparse` qualification chain, including raw SUMO files,
`qualification.json`, hashes and failed-attempt evidence. The copied chain has
109 files totaling 29,283,211 bytes. Raw files live on Omen, not in this public
repository; find their existing locations through the retained acceptance/test
journals. Do not regenerate them merely to make a screenshot.

The original Windows checkout previously showed stale Git stat metadata after
CRLF correction despite identical content. `.gitattributes` now specifies LF.
Do not force-reset, change global Git configuration, or assume `git status`
alone proves a user edit. Existing source-identity checks compare real bytes,
index and Git objects. Prefer an isolated clean checkout if the original
working tree cannot be safely fast-forwarded; preserve all local evidence and
user edits.

## Suggested continuation on the owner's device

These are instructions, **not commands executed after the halt**.

1. Inspect the current checkout, active services and local edits; fetch the
   published source without overwriting user work. Use the existing verified
   CPython 3.12 environment and Node >=22.12.0. Keep package installation
   project-local; the verified npm/SUMO offline bundles are already available
   to the owner. Do not copy Linux `node_modules` onto Windows.
2. Build and test the latest source locally:

   ```powershell
   npm --prefix web run build
   npm --prefix web test
   # For source development, use an unused port; leave the user's demo alone:
   npm --prefix web run dev -- --port 5182
   ```

   If dependencies are absent in a new checkout, install the pinned lockfile
   using the existing verified cache or official npm workflow first. No global
   runtime/settings changes are needed. Follow `preview/README.md` when
   rebuilding a source-bound preview; review and commit its new manifest and
   outputs before using the strict real-replay browser harnesses.
3. Run the authored new camera/signal/layout checks and then real replay
   acceptance on a **new** output directory, reusing the original qualified
   chain. Use `web/tests/desktop_layout_checks.py` for the split-scroll shell,
   `real_replay_smoke.py` for exact genuine matrices/clock/ground contact, and
   the existing desktop smoke. The latter two require the matching strict
   preview. Test pause, play, forward/backward seek, world switching, wheel
   zoom, orbit, deliberate pan, follow reacquisition, end-of-run holding,
   keyboard access and both desktop window sizes. Inspect pixels; matrix
   checks alone cannot establish readable intersections or pleasant tracking.
4. For the genuine API lifecycle gate, follow
   [scripts/API_REAL_ACCEPTANCE.md](scripts/API_REAL_ACCEPTANCE.md). It prepares
   one fixed seed-7 exploratory request ID before POST, retains uncertainty,
   checks exact idempotency and raw replay bytes, and requires terminal state
   before an operator-confirmed restart. Do not retry an uncertain POST or
   reuse an output folder. Existing user-demo port 8765 must be preserved.
   The client supports another loopback origin, but the committed local viewer
   targets 8765; real UI recovery requires a matching source-bound viewer/API
   origin. Do not rewrite a saved journal to hide an origin change.
5. After terminal API verification, use `real_job_recovery_smoke.py` to recover
   the **same** genuine job through the UI with GETs only. This seeds actual
   saved-job state once and checks reload retention; it does not prove that the
   UI originally submitted that job and must not launch a second simulation.
6. Only after correctness/UI/API gates, plan a measured exploratory city scout
   or pilot. See [evaluation/README.md](evaluation/README.md) and
   [evaluation/STUDY.md](evaluation/STUDY.md). A four-case/28-world scout cannot
   authorize the main study; study preparation needs 12–20 complete audited
   pilot episodes. Check previously used seeds first. Qualification seed 7,
   scout seeds and all pilot seeds must remain excluded from study splits.
   Freeze source, whole-demand groups, objective, invalid/censoring rules and
   budget before collection; train/validate before explicit held-out release.
   No honest gain means an inconclusive/baseline-only result, not invented ML.

Tests, browser QA, SUMO and training were restricted to Omen throughout this
work. Cloud performed authoring/static review and explicitly labeled builds,
not acceptance execution. The owner now takes over locally.

## Optional ML dependency blocker

The actual Omen Python 3.12.15 environment has no scikit-learn, numpy, scipy,
joblib or threadpoolctl. `requirements-ml.txt` pins scikit-learn 1.7.2 and defers
installation until a valid pilot and frozen experiment plan.

A cloud download-only Windows bundle was attempted, then rejected by automatic
authorization review; the one clarified retry was also rejected. No completed
archive or wheel/metadata integrity verification exists. A later read-only halt
check found no matching preparation process and only incomplete staging README
and stdlib verifier, not downloaded wheels. No ML packages were installed or
executed. No third-party cache was published, and no account, credential or
payment was created. Do not treat draft staging text as completed verification.

Planned—not delivered—pins were scikit-learn 1.7.2, numpy 2.3.4, scipy 1.16.3,
joblib 1.5.2 and threadpoolctl 3.6.0 for Windows AMD64 CPython 3.12. Official
sources are PyPI version metadata and the exact `files.pythonhosted.org` wheels;
required dependency closure, wheel tags, hashes and licenses must still be
verified. Do not retry the blocked cloud operation or silently choose another
transfer route. The owner may explicitly authorize a new preparation operation
or later install official requirements in their project environment after the
experiment prerequisites. ML can wait behind the requested UI work.

## Submission / truth boundaries

Target submission-ready: November 4, 16:00 IST; recorded deadline: 20:00 IST.
Recheck organizer rules before submission. No submission, paid hosting, new
account or deployment was performed. Hosting work was explicitly deferred.
Keep AI-assistance/library attribution and project freshness disclosures. Never
claim deployment safety, lives saved, trained ML or percentage improvement
without the corresponding real evidence.
