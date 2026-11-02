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
