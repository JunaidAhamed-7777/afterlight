# Freeze a production acceptance candidate

The strict freezer has been used for committed production candidates containing
the real released Study proof. The two prehosting polish passes and the
post-Canva desktop cohort each retain their own source and complete output
inventory. See [prehosting acceptance](validation/prehosting-two-polish-passes.json)
and [post-brand performance](validation/final-desktop-performance.json). Earlier
QA12 remains historical evidence of its exact served files.

The final media/README candidate is still pending. Freeze it only after its
intended source and public assets are committed, then perform the final checks
and hosted file/proof verification against that new inventory. Earlier
acceptance does not automatically transfer to a later build.

Run from the repository root after committing the complete intended source,
public recordings/Study proof, notices, brand/media and deployment configuration.
Install dependencies with the exact lockfile before this workflow; the freezer
never installs packages. Keep source, assets, public data and HEAD stable during
the build.

## Plan, then build

The default only checks inputs, output ownership and tool versions. It performs
no asset preparation, compilation or output writes:

```powershell
$releaseHead = git rev-parse HEAD
python scripts/freeze_production.py --source-commit $releaseHead --output local-runtime/production-final-01
```

Only `--build` prepares the authoritative asset copies and runs the production
compiler. The destination must be a fresh direct child of this checkout's ignored
`local-runtime` directory. Existing candidates are never reused or removed:

```powershell
$frozen = python scripts/freeze_production.py --source-commit $releaseHead --output local-runtime/production-final-01 --build | ConvertFrom-Json
$frozen
```

Build logs go to stderr; stdout contains the compact JSON result. Record the
returned `manifest_sha256` outside the candidate as the acceptance checksum.
Failures retain their partial outputs and any provisional
`manifest.pending.json`. The final `manifest.json` is published only after the
terminal file-set/byte check succeeds, using an atomic no-overwrite hard link.
The local filesystem must support hard links; failure leaves provisional
evidence instead of replacing an existing final file. Require a successful exit
and the pinned verification below before accepting a candidate. Choose a new
destination after correcting a failed build.

## What is bound

The freezer loads the original `build_preview.py` guard from its exact committed
source bytes. It reuses that guard's `snapshot`, `environment`, `tool_commands`
and `safe` functions unchanged. The supplemental checks cover every public file
and the deployment/freezer configuration, including replays, Study, notices,
brand and media. HEAD, index and actual committed bytes must agree.

`web/public/assets` is reserved for the 18 prepared copies of authoritative
exports, map and previews. Its complete file set and hashes must match the root
assets, with no stale extras. Put additional public brand/media files in their
own committed public folders or use committed source imports.

Preparation occurs before the full pre-build inventory, and cannot change any
authoritative input. The actual static build environment removes inherited
`VITE_*`, `NODE_OPTIONS`, `NODE_ENV` and inherited `npm_config_*` values without
case-sensitive gaps; `VITE_API_BASE` is genuinely unset. Distinct verified-absent
user/global npm config paths are pinned inside the fresh candidate, so external
npm configuration cannot restore a preload or configured lifecycle shell. These
paths must remain absent before and after tool/preparation/build calls. The
original repository/web `.npmrc` rejection remains unchanged. Secret environment
values are never recorded. Full input, prepared-mirror, tool-version and
license-byte inventories must remain equal after compilation.

Before any Node/npm calls, the wrapper also rejects direct repository/web
filenames matching `.env*` or `.npmrc` without case-sensitive gaps, including
Windows aliases such as `.ENV` or `.NPMRC`. It never reads their contents.

The build writes directly into the fresh candidate's `site` directory. Every
output file and its exact byte count/hash are recorded; the complete site must
remain below 50,000,000 bytes. The manifest stays **outside** the served site.
It retains `files`, `total_bytes` and `source.head/source_sha256` for the existing
browser/video harnesses. It also records the full strict inputs, actual argv,
environment policy and measured tool identities.

Actual tool paths remain in this ignored local manifest. Do not publish that
manifest as a public asset or copy its machine paths into public records. The
underlying tool guard checks installed versions and license bytes, not every
installed dependency byte; it does not claim universal cross-platform build
identity.

## Check before and after acceptance

Use the externally recorded checksum to detect changes to either the manifest
or its complete output file set:

```powershell
python scripts/freeze_production.py --verify local-runtime/production-final-01/manifest.json --manifest-sha256 $frozen.manifest_sha256
```

This read-only output check detects added, missing or altered files. It loads
current committed guards, so main can advance after freezing without relabeling
the candidate's original source commit. It does not claim current source inputs
still equal that historical candidate. Keep the external checksum in the
acceptance record; checking an unpinned, rewritten manifest alone cannot prove
that a candidate stayed unchanged.

Serve only `site` on a free task-owned loopback port; 5204 is an example:

```powershell
python -m http.server 5204 --bind 127.0.0.1 --directory local-runtime/production-final-01/site
```

Pass `local-runtime/production-final-01/manifest.json` to the existing acceptance
and final video commands through `--build-manifest`. Run the complete pinned
file-set check before and after each formal pass and capture. A changed served
file requires a fresh candidate and appropriate verification, rather than an
edit to the frozen site.

Focused tests use tiny committed-tree fixtures and mocked preparation/build
commands only:

```powershell
python tests/preview/test_production_freezer.py
```
