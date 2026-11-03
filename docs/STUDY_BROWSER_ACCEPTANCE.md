# Released Study browser acceptance

This is a prepared workflow. **Do not run it until the actual audited public
Study pack has been released.** There are no positive fixtures, guessed results,
local outcome-directory inputs, or unpublished-report fallbacks.

Set `$publishedManifestSha` to the exact manifest SHA-256 recorded by the
completed release, and use a fresh output directory:

```powershell
.\.venv\Scripts\python.exe web/tests/study_positive_acceptance.py `
  --base-url https://YOUR-VERIFIED-DEPLOYMENT.vercel.app/ `
  --released-manifest-sha256 $publishedManifestSha `
  --output local-runtime/released-study-browser-01
```

An optional `--build-manifest` binds every served build file before and after
the check, using the same isolated-build inventory as desktop acceptance.

## Public evidence verification

`released_study_pack.py` performs independent HTTP GETs. It verifies the explicit
manifest hash, the summary's original byte count and SHA, and every listed
companion's bytes and hash. Bounds are 16 KiB for the manifest, 1 MiB for the
summary, and 4 MiB for each physical companion download. The complete proof pack
also stays within its agreed 4 MiB physical budget. Artifact paths must remain
local to the publication; redirects and unsupported encodings are rejected.

The verifier reconciles public study, protocol, selection, release, report,
selector and optional model envelopes. It checks the model's frozen source,
protocol, training-data hash and training-group separation. Every test episode
must appear once per comparison in both the report and the complete-case CSV.
Unavailable objectives must stay blank in CSV instead of becoming zero.

Failure/status counts, paired objective and component means, changed-action
rates, and whole-demand-group intervals are recomputed from the public records.
Missing intervals retain their actual reason and independent-group count.
Declared regime and route-family holdouts and excluded exploration seeds are
checked against the published inventory. Private simulator outcomes are never
opened, and no traffic, training, selector fitting or test release is run.

The agreed reproduction pack also includes lossless XZ copies of the original
train/validation candidate grids and test candidate/full-scalar outcomes.
`reproduction.json` binds their physical transfer hashes, original decoded hashes,
and frozen source-file identities. Decoding uses a 128 MiB output bound and a
128 MiB decoder-memory cap; trailing or concatenated streams are rejected.

The verifier checks the local pure scientific helper source bytes against the
released source inventory before using them. It also binds all nine actual
module files, import specs, loader paths and package paths; foreign cached
modules are rejected. Verified source bytes are compiled directly, so path
shadowing and stale bytecode cannot supply the recomputation helpers. JSON
numbers that overflow to infinity are rejected along with duplicate keys and
nonstandard NaN/Infinity tokens.

It recomputes the validation-tuned
fixed choice and the frozen model/comparator choices from the released lagged
observations and candidate grids, then reconciles the complete report against
the full seven-world scalar inventory. It does not refit a model or run SUMO.

The isolated guard checks can run before publication. They use synthetic
temporary modules and JSON bytes, with no Study pack or outcome inputs:

```powershell
.\.venv\Scripts\python.exe web/tests/test_released_study_guards.py
```

These checks are also included in the default `units-network` acceptance plan.

## Browser checks

The headed desktop check opens a genuine public recording and pauses it with
Follow Ambulance active. This run must not fetch Study data. The actual Study
view must show the released episode/world/group counts, failures, status totals,
paired means with their signs, interval or missing reason, holdouts, provenance,
and correctly labeled artifact downloads. Browser response hashes must match the
same real publication verified independently.

The test then supplies one deliberately invalid manifest response. After that
error, routing is removed: keyboard Retry must fetch the **real server pack** and
focus the actual ready heading. A valid Study body is never mocked or fulfilled
by the harness.

Mounting and leaving Study must preserve the recording, clock, traffic world,
follow target and camera. Both Skip and Done are checked through Study → Settings
→ Show the guide → exit → Results, which must return to This run.

The JSON report and actual PNG screenshots are saved under the selected
`local-runtime` directory. The final positive check, two whole-product polish
passes and final media capture remain separate release steps.
