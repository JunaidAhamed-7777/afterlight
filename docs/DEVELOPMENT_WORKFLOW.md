# Development workflow

AFTERLIGHT's public repository is the project source of truth for implementation, documentation, original assets and validation evidence.

## Frequent, meaningful commits

Per the project owner's instruction, commit and push very frequently: after each small coherent improvement, bug fix, test addition, documentation correction or verified asset revision. Do not accumulate an entire feature's work into one late commit.

- Keep each commit focused and reviewable; describe what changed and relevant checks.
- Run the smallest applicable checks before publishing. Clearly record untested behavior instead of claiming validation.
- Preserve working checkpoints. Do not publish knowingly broken code on `main` merely to increase commit count.
- Include changed requirements or verification notes alongside the work they describe.
- Re-read the current branch head before writes, preserve other contributors' edits and use a non-forced expected-head update.
- Never commit secrets, local runtime state, dependency caches, private captures or unlicensed third-party assets.
- Keep canonical assets and their manifests consistent after regeneration. Validate geometry, coordinates and exports independently of visual polish.

Small commits are a recovery and review tool, not a numerical goal. Do not fabricate progress, create empty commits or rewrite published history to inflate activity.

## Development and acceptance locations

Implementation is performed on the cloud PC. At the owner's request, all tests, browser QA, benchmarks and training/experiment execution are performed on Omen in `C:\Github\afterlight`. Cloud build/compilation may support development but must not be presented as acceptance testing. Each checkpoint records its commit and exact local commands; pending checks remain explicitly unverified. Return local failures to the implementation owner, publish a focused fix, and rerun affected checks locally. Do not work around cloud WebGL restrictions or substitute synthetic evidence for a local result.

## Reproducible compiled preview assembly

`scripts/build_preview.py` is a cloud/Linux development-build helper, not a test
runner or Windows installer. Commit the complete frontend/helper/assets first.
With the existing locked npm dependencies installed:

```sh
python scripts/build_preview.py --source-commit <full-current-HEAD>
python scripts/build_preview.py --source-commit <full-current-HEAD> --build
```

The first command only inspects the plan. The second explicitly compiles public
and loopback-API entries into fresh scratch directories, checks actual source
bytes/index/HEAD and installed package versions, preserves required copyright
notices, and assembles owned preview files with exact hashes. It rejects local
`.env`/repository npm overrides; it does not install dependencies or execute tests.
Matching installed versions is not a substitute for package-byte integrity or
Omen's independent source-install/build gate. Old chunks and unrelated files are
preserved rather than broadly deleted. Publish the new manifest and referenced
outputs together, then run exact-hash and desktop browser acceptance on Omen.
