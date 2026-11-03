# Source-bound application preview

This is a compiled AFTERLIGHT application for dependency-free local viewing.
Python serves its existing JavaScript, assets and public recordings; Node/npm
are required to rebuild it, not to serve it. `manifest.json` is authoritative for
the compiled source commit and every declared source/output/runtime-asset hash.

Run verification before using the preview. A stale or edited input must fail;
do not bypass the guard or replace hashes to make a different source appear
accepted. Existing preview files can intentionally lag source during development.
Preserve a historical checkout when an older accepted preview is still needed.

## Serve a verified preview

```powershell
python scripts/serve_preview.py --verify-only
python scripts/serve_preview.py --port 5173
```

Use an unused loopback port. `/` uses the public recorded catalog;
`/local.html` is compiled for the separately started API at
`http://127.0.0.1:8765`. Its capability comes from that server; the page neither
installs SUMO nor starts a backend. Keep existing user demo services intact.

Runtime exports, the canonical map and the expanded static fallback are served
from authoritative repository asset paths. Recordings come from
`web/public/replays/`; the current catalog contains genuine 0.5 s pairs in lossless
gzip containers. Never register a synthetic test fixture as public traffic.

## Rebuild on Windows, Linux or macOS

Commit the complete source/helper/assets first, and install the pinned lockfile
in `web/node_modules`. The helper never installs dependencies or runs tests.
It resolves Node and the installed npm JavaScript CLI directly, including on
Windows; it does not invoke a batch shim through a shell.

```powershell
$previewCommit = git rev-parse HEAD
python scripts/build_preview.py --source-commit $previewCommit
python scripts/build_preview.py --source-commit $previewCommit --build
python scripts/serve_preview.py --verify-only
```

The first helper call is read-only planning. The second compiles public and
local-API entries into fresh temporary outputs. It checks exact working bytes,
HEAD/index identity, locked runtime versions and retained licenses before/after
compilation, records tool identity, then atomically publishes owned preview files
and its manifest. Source drift refuses publication; partial owned writes roll
back. Unrelated files and obsolete chunks remain intact. Publish the new manifest
and referenced outputs together, then perform current headed desktop acceptance
from [web/README.md](../web/README.md). A compilation is not browser or scientific
acceptance.

## Historical checkpoints and line endings

The previously accepted smaller-city viewer was `3060716`, compiled from
`975dd295a7f3ca06e42b814c616b77108b6fced7`. Its 187-building V3 scene, checks and
public-empty/local-catalog state belong to that historical cohort. At the owner
halt, later desktop source had not been rebuilt. Those results do not validate
the expanded city, dense recordings or later UI.

The repository requires LF text through `.gitattributes`. Do not change global
Git settings, reset user edits or normalize arbitrary files to defeat byte
verification. `scripts/refresh_preview_checkout.py --refresh-clean-checkout`
is only for the specifically checked-out historical preview cohort described
by its manifest. It proves clean tracked/indexed content before refreshing exact
manifest-listed bytes. A refusal is evidence to investigate, not a guard to
remove. Source-bound builds always compare real working bytes against HEAD.

Runtime-library copyright notices remain in `licenses/`. Matching installed
versions is not verification of every dependency byte or a substitute for the
independent source-install/build gate. Keep measured browser performance,
traffic validity and trained/held-out results in their own acceptance records.
