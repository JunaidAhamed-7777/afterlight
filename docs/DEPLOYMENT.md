# Zero-cost delivery

## Chosen baseline

Run SUMO generation, fitting and evaluation locally. Publish a static React/Three.js viewer on a free static host such as Cloudflare Pages, with versioned recorded traces and benchmark summaries. No paid API, persistent server or cloud GPU is necessary. Provider limits and terms must be rechecked before deployment.

Cloudflare Pages static requests are documented separately from metered Functions. Avoid Functions for the MVP. Its documented maximum individual asset size is 25 MiB; split scenario traces and keep meshes below it. Do not depend on a video larger than the asset limit: publish the demo via the contest-supported video route after checking its terms.

## Truthful public capabilities

The public viewer can switch among exported scenarios, scrub synchronized outcomes, inspect decision inputs/actions and read results. It cannot claim to run arbitrary fresh SUMO experiments. Label sample selection and prerecorded provenance visibly. ONNX/browser inference is a stretch only if preprocessing and outputs are verified against Python; it is unnecessary for a credible entry and does not move SUMO into the browser.

## Release gates

- Local commands independently reproduce one small scenario and benchmark aggregation.
- Every public trace maps to a versioned manifest and matching code/config.
- Build output contains no environment secrets, email details or private notes.
- Asset sizes, MIME types, loading/error states and WebGL fallback checked.
- Attribution and dependency/asset licenses included.
- Submission URL and repository work from a logged-out browser.

If hosting is blocked, local code plus a strong truthful demo remains the fallback because deployment is recommended rather than mandatory. Spend no money to rescue deployment. Final README must state what runs locally versus what the public URL actually does.

## Expanded product capabilities

Public static mode may expose the city, pickup/hospital catalog and only prerecorded combinations actually available, with clear unavailable states. It cannot run arbitrary randomized demand by pretending a new seed has been simulated. Local live mode is separate and advertises only implemented validated routes. Both share ghost/world-isolation semantics, error/retry behavior and accessible metrics. Preload the minimal map; lazy-load scenario traces and optional detail rather than shipping every pickup combination upfront. No new paid storage account is assumed.
