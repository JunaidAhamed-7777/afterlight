# AFTERLIGHT — current handoff

## Current release checkpoint — November 4, 2026

AFTERLIGHT is a desktop replay and evidence product. The expanded city has exactly four times its original area, 81 primary intersections, 826 original Blender buildings, 100 pickup anchors and two hospitals in diagonal quadrants. Cars, bikes and trucks follow recorded SUMO traffic. The fixed right viewport holds camera and playback controls; Simulation, Results and Settings scroll independently on the left. Loading, cancellation, onboarding, dual follow, actual-model legends and 10×/20× playback have scoped desktop acceptance.

The two public exploratory pairs retain every 0.5 s integration step and the final 3 s city clearance. Cross-city ambulance journeys are 601 s ordinary versus 473 s fixed priority, with civilian mean excess time +2.19 s. Westhaven is 426.5 s versus 322.5 s analytical priority, with civilian mean excess time +1.14 s. All civilians finish in these examples with zero collisions. Their [qualification](docs/validation/expanded-city-qualification.json) and [9,839-crossing presentation review](docs/validation/expanded-city-presentation.json) are bounded evidence, not held-out superiority or universal safety certification.

The frozen study at `fa39f8a` has 24 training, 12 validation and 20 test episodes. Its original single test attempt audited all 140 worlds: 134 completed and six invalid. The learned selector chose the same action as analytical in all 20 test episodes; both have one failure and zero finite objective difference. Against validation-tuned fixed 5 s, learned has one failure versus zero. The 19 finite pairs have mean objective delta **+0.681 s**, with 95% grouped interval **−4.993 to +5.978 s**. Component deltas are +0.632 s ambulance journey and +0.049 s civilian mean excess. Deltas are selected minus comparator; lower is better. This does not establish a learned improvement. Preserve the [complete negative result](docs/validation/study-v4/report-checkpoint.json).

The original pre-fit metadata failure remains retained. A separately frozen [analysis amendment](docs/ANALYSIS_AMENDMENT.md) binds the exact full estimator, preserving the original simulation checkout, protocol, inputs and raw outputs. One fresh amended selection fitted the predeclared 11-node tree; the subsequent exclusive test attempt is complete. No further fitting, test retry or outcome-dependent tuning is authorized by this handoff. Main's future verifier correction at `989c1ee` does not replace the present study's amendment or source identity.

The [28-file public Study pack](docs/validation/study-v4/publication.json), 2,405,037 bytes, is published. The [actual public CLI and Study UI acceptance](docs/validation/study-v4/public-browser-acceptance.json) passed against explicit manifest SHA `f5b3b10f59c4daf3b77aaa9aaec971d7b7f7ac85c95027021bbfaa305ae1aea9`. It verifies original companions, complete grids, frozen choices, failure accounting and grouped intervals. Public metadata does not independently prove human test nonaccess. The interface replays cached evidence; Vercel does not run SUMO or a live learned controller.

The [two separate prehosting polish passes](docs/validation/prehosting-two-polish-passes.json) are complete, recorded at `5aec54b`. [First public Vercel acceptance](docs/validation/production-hosting-first-acceptance.json), checkpoint `23765b7`, preceded the actual [Canva identity and frontend implementation](docs/validation/canva-identity-implementation.json) at `fa0d88c`. The post-brand deployment `dpl_Fg238DsG3ByVPPMGbP8yPqHWYHmY` is READY at [the public site](https://afterlight-gamma.vercel.app/). The refreshed README and first genuine walkthrough are committed. A small 1280 px results-table wrap was then corrected; a replacement walkthrough and final hosted acceptance are pending.

[Post-brand performance](docs/validation/final-desktop-performance.json) measured **161.8 FPS overview / 127.7 FPS close follow**, each over an actual 30 s visible, focused headed-Chrome window. This is one Ryzen 9 5900HX/AMD integrated-GPU profile, with 373 vehicles at measurement start, 1920×1080 CSS viewport at DPR 1, native window 1724×978 and actual canvas buffer 1552×737. It measures browser render cadence, not completed GPU time, inference or simulation speed. Earlier failed and unqualified attempts remain recorded. Independent pixel review passed on 26 unique post-brand camera, follow, notices and Study PNGs; [the post-identity acceptance record](docs/validation/postbrand-desktop-acceptance.json) retains the review and exact-repeat checks.

### Remaining release work

- Finish the complete source-test checkpoint and inspect the replacement native walkthrough. Candidate 01 and its minor results-table wrapping issue remain retained.
- Refresh README media facts after the replacement capture. The first complete media build is 46,956,618 bytes; verify the final replacement inventory below 50 MB.
- Redeploy the final media/documentation cohort, verify exact hosted files and public proof, and reconcile final handoff/roadmap state.

Keep all original scientific journals, failed attempts, historical checkouts and immutable build candidates. Desktop only; no mobile work is required.

The preceding release checkpoint is retained in [the archive](docs/archive/HANDOFF-20261104-pre-release.md).
