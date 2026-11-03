# Static Vercel delivery

## Deployment target

Vercel is the chosen production target. The repository-root `vercel.json` builds
the static React/Three.js product; SUMO, fitting and local-generation jobs remain
on the operator's computer. No public simulator API or hosted function is part
of this deployment.

Project settings follow the committed configuration:

- Root directory: repository root.
- Install: `npm --prefix web ci`.
- Build: `npm --prefix web run build`.
- Output: `web/dist`.
- Framework preset: no automatic framework detection (`framework: null`).
- Production `VITE_API_BASE`: leave unset so the site uses its bundled catalog.

The asset preparation step copies authoritative exports/map/previews into the
build. `.vercelignore` excludes local environments, raw experiment directories,
Blender scenes and source-only research folders. It keeps the exports, canonical
map and public recording files needed by the build. Check the actual upload and
build inventory before release; never infer readiness from this plan alone.

## Recording transport and budget

The current catalog publishes two real 0.5 s exploratory pairs with 3 s all-red
clearance as `.json.gz`. Together they occupy exactly 13,304,439 bytes
(13.30 MB) of compressed recording files. The current
city GLB is 14.38 MB. The owner permits at most 50,000,000 bytes of shipped static
assets, including recordings; measure the complete output, not only the meshes.

Catalog `bytes` and `sha256` bind the original decoded JSON. `encoding`,
`transfer_bytes` and `transfer_sha256` describe the compressed container. Serve
`.json.gz` losslessly: the viewer handles gzip magic bytes or an HTTP-decoded
response. Do not relabel compressed bytes as JSON without matching transport
behavior. Each decoded response is capped at 128 MiB independently of the static
asset budget. A worker prepares one selected recording; benchmark its actual
load latency and memory on desktop.

The committed cache headers require revalidation for catalog/replays, canonical
maps and named GLB exports. Deploy those files as a consistent build. The browser
rejects mismatched recording metadata/checksums and mismatched city hashes rather
than presenting stale traffic on a different map.

## Release verification

Build and run the current headed desktop acceptance against an isolated output
and its manifest. Verify initial loading, both recordings, exact world switching,
seek/ghost behavior, keyboard access, errors, and 16:9 layout. Retain actual
renderer/frame-time/memory measurements with device and resolution. Inspect
multiple camera tilts and yaws for depth fighting. Foreground building reveal
starts enabled on every visit; intentional partial building fades are expected.
Disable reveal explicitly when checking the opaque depth baseline.

After the hosting tool reports a ready deployment, verify the returned URL and
its public assets from an unauthenticated browser. Confirm HTTPS loading, gzip
behavior, base paths and absence of loopback API calls. Record the exact source
commit/build identity and production URL in the release documentation. Rebuild
and redeploy after later identity/frontend changes; an earlier URL does not
validate newer source automatically.

Public capabilities are replay, exploration and evidence inspection. Arbitrary
pickup/seed generation is available only through an explicitly enabled loopback
runner. Its real job lifecycle and completed recordings stay distinct from live
streaming. The local API must not be exposed by a public tunnel as a deployment
shortcut.

## Historical hosting proposal

The initial plan considered Cloudflare Pages and its then-documented 25 MiB
individual-file limit. That was a proposal, not a deployment or a Vercel quota.
The original 25 MB map ceiling was later superseded by the owner's 50 MB total
asset allowance. Historical provider limits and old prototype inventories do not
define the current release. Verify applicable provider terms before publishing.
