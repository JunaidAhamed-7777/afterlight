# Released Study browser acceptance

The audited Study pack is published at
[the public lab](https://afterlight-gamma.vercel.app/). Actual-data browser
acceptance and independent public recomputation have completed. The
[publication record](validation/study-v4/publication.json),
[actual Study browser acceptance](validation/study-v4/public-browser-acceptance.json),
[post-identity browser review](validation/postbrand-desktop-acceptance.json) and
[public HTTPS acceptance](validation/production-hosting-postbrand-acceptance.json)
retain their original checks and hashes.

For any future pack, **run this workflow only after its actual audited public
release**, using that release's exact manifest SHA-256 and a fresh output
directory. There are no positive fixtures, guessed results, local outcome-directory
inputs, or unpublished-report fallbacks. For the current publication:

```powershell
$publishedManifestSha = 'f5b3b10f59c4daf3b77aaa9aaec971d7b7f7ac85c95027021bbfaa305ae1aea9'
.\.venv\Scripts\python.exe web/tests/study_positive_acceptance.py `
  --base-url https://afterlight-gamma.vercel.app/ `
  --released-manifest-sha256 $publishedManifestSha `
  --output local-runtime/released-study-browser-01
```

An optional `--build-manifest` binds every served build file before and after
the check, using the same isolated-build inventory as desktop acceptance.

## One-command public reproduction

Recompute the current published pack from the repository root with its exact
released manifest identity:

```powershell
python scripts/verify_public_study.py --base-url https://afterlight-gamma.vercel.app/ --released-manifest-sha256 f5b3b10f59c4daf3b77aaa9aaec971d7b7f7ac85c95027021bbfaa305ae1aea9
```

It uses Python's standard library and the repository's original pure inference
helpers. It needs no browser, SUMO, model fitting, optional ML installation,
private outcome directory or local unpublished report. It prints actual split
and world counts, paired comparisons/failures, grouped intervals and proof
results after the complete public verification succeeds.

Optional `--output local-runtime/public-study-proof.json` saves the public
verification result to a **fresh** JSON file. Its parent must already exist;
existing files are never overwritten. Failed verification prints no success
result and creates no report.

The CLI and shared proof helper refuse optimized Python (`-O`, `-OO` or enabled
`PYTHONOPTIMIZE`) before verification/network access, because the proof code
uses assertions. The isolated negative CLI/import guards block DNS and sockets
and can run before publication:

```powershell
python web/tests/test_public_study_cli.py
```

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

The original exclusive test-attempt envelope and completed collection manifest
are published as `attempt.json` and `collection.json`. Their exact original
hashes must match the report; the attempt's logical hash must also match the
release-bound claim identity. The verifier reconciles release/study/protocol,
source/dependencies/SUMO, the claimed-before-first-world state and declared
release → claim → collection → report chronology. Every declared case retains
ordinary, immediate and all fixed candidates exactly once as audited/invoked
worlds. Full scalar rows must match those original inventory directories.
These metadata checks cannot independently prove absence of other private
attempts, human nonaccess or the physical location of original files.

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

## Explicit analysis amendment

The original simulation checkout and frozen study/protocol stay unchanged. A
documented pre-test correction may use the exact frozen estimator configuration
when validating collected analytical predictions, instead of reconstructing a
default configuration with a different JSON numeric representation. It must not
coerce hashes, rewrite collected data, or replace the original scientific helpers.

An amended publication must include its original descriptor, statically vendored
verifier and binding helper, entrypoint, reviewed diff, and original failed-attempt
log and journal. The public verifier checks all seven companions' exact bytes and
hashes. The descriptor must bind the original study/protocol/simulation source,
the exact whole-estimator hash, both original module hashes, and the failed
verification before model fitting. Integer `1` and float `1.0` are not treated as
the same frozen JSON identity.

Every descriptor filename must match its explicit public artifact URL. The
byte-exact failed log and journal use `analysis-failure.txt` and
`analysis-failed-selection-journal.json`; their original hashes remain binding.

Selection and report must bind the same descriptor and implementation hashes.
The original release must bind the complete amended selection envelope and its
original file bytes. Declared creation times must put the amendment before
selection, then release, then report. These metadata checks do not independently
prove human nonaccess or when fitting actually began.

The failed dependency-watcher journal must record a stopped attempt, return
code 1, zero automatic retries, and timestamps preceding the amendment.
Contradictory success or fit-completion markers are rejected. The original
journal has no fit-stage marker: the descriptor's pre-fit statement relies on
the retained stack/log and the reviewed absence of the original output, rather
than an independent journal proof that fitting never began.

Downloaded analysis sources are hashed, never imported or executed. Frozen
decision recomputation still uses only the original nine byte- and origin-bound
pure scientific modules. The browser must show the amendment disclosure and its
downloads, with the original Git link labeled **Simulation source commit**.

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
