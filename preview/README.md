# Source-bound application preview

This is a compiled AFTERLIGHT application, not an offline package cache. It lets a
Windows tester use the existing Python and browser while npm downloads are
unreliable. Runtime library and emitted Vite runtime-helper MIT notices are in `licenses/`. Original authored
GLBs/map/preview are served from their existing repository paths, not duplicated.

**Compiled source:** `92cc07dc1efb98a13e5ae843308f6ab3d7968e7d`.
`manifest.json` records source, output and original asset SHA-256 hashes. The
server refuses missing/changed inputs rather than quietly testing stale code.
Compilation succeeded in the cloud. This build includes strict bounded browser JSON handling, V3 modeled city details, canonical map selection and the offline selector evidence inspector and descriptive individual-civilian delay-tail row. At `11be524`, Omen passed the source/desktop suites and focused V3 pointer, fade and layout checks for this build. Real city traffic playback remains unaccepted. Exact scoped evidence is recorded in `docs/validation/OMEN_LOG.md`.
A successful preview test does not establish npm installation reproducibility,
SUMO correctness, performance improvement, or a trained model.

## Omen commands (repository root)

```powershell
python scripts/serve_preview.py --verify-only
python scripts/serve_preview.py
```

Open `http://127.0.0.1:5173/` for public recorded mode. The initial empty catalog
is intentional: no genuine SUMO pair has yet been generated and accepted. Check
loading, original city assets, controls, keyboard, desktop window resizing, errors and WebGL. Mobile optimization/testing is outside the current target.
`http://127.0.0.1:5173/local.html` is compiled for the local API at
`http://127.0.0.1:8765`; it should show an honest disconnected state until that
API is running. See the root README for API prerequisites and explicit generation
opt-in. This page does not supply missing Python/SUMO dependencies.

Keep the server loopback-only. No system configuration, symlinks or admin rights
are needed. Stop it with Ctrl+C. Catalog/replay files are read from
`web/public/replays/`, allowing later genuinely audited recordings without
rebuilding JavaScript. Do not register synthetic test fixtures as real runs.

## Reproducing the compilation

The preferred cloud/Linux source-bound helper is documented in
[development workflow](../docs/DEVELOPMENT_WORKFLOW.md). It builds both entries
and assembles the manifest without running tests. The equivalent underlying
compilation commands, with locked dependencies installed, are:

```sh
npm run build --prefix web
VITE_API_BASE=http://127.0.0.1:8765 npm run build --prefix web -- --outDir ../local-runtime/preview-local-build --emptyOutDir
```

The second command uses POSIX environment syntax; PowerShell uses
`$env:VITE_API_BASE='http://127.0.0.1:8765'` before the build and
`Remove-Item Env:VITE_API_BASE` afterwards. Copy static `web/dist/index.html`
and direct `web/dist/assets/*.js,*.css` into `preview/site`; copy the local build
index as `local.html` and its direct JS/CSS alongside. Do not copy asset subfolders
or node_modules. Copy the authored `favicon.svg` to `preview/site/` too. Regenerate the manifest against the new committed source and
retain runtime copyright notices. The two renderer chunks differ because their
entry-module import bindings differ; both are necessary for these two builds.

## Windows checkout line endings

The repository now requires LF text through `.gitattributes`; binary assets stay
binary. An existing checkout created with `core.autocrlf=true` may retain CRLF in
unchanged files after fetching the attribute commit. Do not change global Git
settings or weaken hash verification. After checking out the instructed preview
cohort, use the explicit, targeted refresh:

```powershell
python scripts/refresh_preview_checkout.py --refresh-clean-checkout
python scripts/serve_preview.py --verify-only
python -m unittest discover -s tests/preview -v
```

The helper checks every manifest-listed text input is tracked and has no staged
or unstaged content edits, then reads their indexed Git blobs, verifies every blob against the manifest,
and atomically replaces only inputs whose exact bytes differ. It rechecks for
concurrent edits before each replacement, verifies all resulting hashes, and
requires Git content-clean postconditions before reporting success. If it refuses, preserve the edits and report the exact mismatch; do
not reset the worktree or force through the preflight. Files outside those listed
inputs are untouched. The manifest still checks exact SHA-256 bytes, including
the original canonical map JSON and unchanged binary GLBs.

Git checkout-index may leave a clean CRLF file untouched even with `--force`;
this helper deliberately does not rely on that command or its exit status as
evidence that bytes were rewritten. It never changes index content or global
configuration. If any postcondition fails, stop and report it rather than
starting the application on unverified inputs.
