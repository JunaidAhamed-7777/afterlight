# Read-only study publication

The viewer's **Study** results are separate from **This run**. A public recording
is an exploratory fixed/analytical demonstration. The study view describes a
released comparison of frozen selectors over cached, real SUMO candidate
outcomes. It does not turn the viewer into a live learned controller.

Until an actual audited report is published, the viewer says that results are
not published. Synthetic schema fixtures belong only in tests and must never be
copied into `web/public/study/`.

After actual report creation, run the main checkout's helper against the clean
pinned scientific checkout:

```powershell
.venv\Scripts\python.exe scripts/export_study_summary.py --checkout C:/Github/afterlight-final-study-v4 --study local-runtime/expanded-city-study-v4 --train local-runtime/study-train-v4 --validation local-runtime/study-validation-v4 --collection local-runtime/study-test-v4 --report local-runtime/study-report-v4 --analysis-amendment local-runtime/analysis-amendment-v1/analysis-amendment.json --output local-runtime/study-public-pack-v4
```

The directory names above are examples; use the original frozen study,
single-attempt released test collection and report. The destination must be new,
inside the pinned checkout's `local-runtime`, and separate from all original
evidence and the frozen selection directory. A failed export stays retained and
is not publishable.

The helper imports verification from that explicit checkout. It recomputes the
full report and grouped intervals from the original released evidence before
projecting the summary. It neither simulates nor fits, chooses new actions,
creates a release, or rewrites original artifacts. Copied selection/model bytes
must match the pre-test release's exact hashes.

An amended selection/report requires the explicit `--analysis-amendment` above.
The exporter checks the separate frozen descriptor against the original source
and exact estimator before loading its verified raw analysis source bytes. It
requires the selection/report bindings to agree and rechecks the same descriptor
identity before its completion marker. All seven descriptor/source/patch/failure
companions are copied with original byte hashes. The public verifier checks
these companions without executing downloaded analysis code.

The output contains a bounded `manifest.json`, `summary.json`, and exact original
report, study, protocol, selection, release and selector companions. Learned mode
also includes the original safe JSON model. A per-case CSV retains every test
scenario under each comparison, including unavailable objectives and statuses;
numeric differences keep their original precision. Copy this verified pack into
`web/public/study/` as one publication. The UI verifies the summary's original
UTF-8 byte count and SHA256 before schema validation; all companion links remain
relative to the same study directory. Manifest and summary limits are 16 KiB and
1 MiB respectively.

The reproduction companions also retain the **exact original** training and
validation candidate grids, test candidate grid and full test scalar outcomes.
These include every queue sample and lagged observation. Each is a single
lossless XZ stream, bounded at 4 MiB physical / 128 MiB decoded with a 128 MiB
decoder memory limit. `reproduction.json` binds original decoded hashes to the
pre-test selection or final report, separately from physical download hashes.
No JSON rewriting, row omission or temporal downsampling is used. The normal
viewer links these optional downloads without decoding them eagerly.

Original learned/fixed/analytical selector and frozen comparison envelopes are
copied with their pre-test release byte hashes. The four grid input paths are
explicit; the exporter does not scan directories for alternate datasets. The
complete pack has a default 4 MiB physical ceiling. If it exceeds that allowance,
publication fails; retain all data and revise the optional media budget rather
than silently dropping evidence. Its completion manifest is written last.

Every comparison includes failures over the full test denominator, status counts,
the paired-complete denominator, signed mean differences and the objective's
grouped 95% interval when at least ten independent groups support it. All means
and intervals are conditional on both selected outcomes completing validly.
Missing values stay null. A selected failure means the objective is unavailable;
it can include a completed world without a finite target. No automatic benefit
badge is produced.

The summary's `report_sha256` is the original report envelope's logical digest;
`report_file_sha256` binds its exact published bytes. `model_sha256` is the exact
model file hash frozen in the release, not the model envelope's logical digest.
Each companion also has its own exact file checksum and byte count.

`tests/acceptance/test_study_summary.py` uses explicitly synthetic data to check
projection, failure retention, original-evidence protection and both learned and
baseline-only compatibility with the production TypeScript validator. These
tests are contract checks, not scientific experiment results.

## Reproducible README figure

Use a separate plotting environment so installing figure tools does not change
the study's pinned runtime. Its resolved versions are recorded in
`docs/validation/study-v4/plot-requirements-lock.txt`.

```powershell
local-runtime\plot-env-v4\Scripts\python.exe scripts/render_study_figure.py --pack C:/Github/afterlight-final-study-v4/local-runtime/study-public-pack-v4 --output local-runtime/study-figure-v4
```

This command requires the actual verified pack. It checks the manifest, original
study/report digests, every plotted difference and each interval against the
original report records. It produces PNG/SVG plus a render manifest with the
input hashes, library versions and palette. There are no fallback metrics.
Apply the final identity with `--accent`, `--background` and `--ink`; use a fresh
output directory directly under the main checkout's `local-runtime` for each
render. Inspect the actual figure before publishing.
