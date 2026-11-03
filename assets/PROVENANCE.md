# Asset provenance and publication status

| Item | Origin | External assets | Distribution status |
|---|---|---|---|
| Ambulance, civilians, building kit | Newly authored procedural Blender geometry for Afterlight | None | Original project work; owner selects project license |
| City roads/buildings/hospitals/parks | Canonical seeded city manifest + authored Blender geometry | None | Original project work; owner selects project license |
| Ghost appearance | Shared ambulance geometry + authored material recipe | None | Original project work; owner selects project license |
| Source scripts | Authored for Afterlight | Python/Blender runtime APIs only | Original project work; owner selects project license |

Blender 4.3.2 and the existing pinned Blender MCP addon were authoring tools. Neither addon source nor third-party model assets are included in the public delivery pack. All materials are parameter-based, with no image textures. The amber pulse emblem and fictional hospital names are original project identifiers. No protected Red Cross emblem or actual emergency-service branding is used.

The expanded V4 city was newly authored on November 3, 2026 in Blender 5.2.2 LTS
through the same existing MCP addon, pinned to upstream
`febcd90ece59c3416d7c55fd3723cea46bcaa59d` / SHA-256
`8e193a249e2ed1262f3e794ee2254efd8e3d1f0224385245f2b989154c837083`.
`src/generate_city_v4.py` constructs the expanded original city directly from the
canonical map. The streetlights, park fountains, trees, facade/roof details and
hospital identities are original procedural geometry. `afterlight_city_expanded.blend`
is its editable source; the exact generator/map/GLB hashes are recorded in the
companion export manifest. Existing ambulance, civilian and original prototype
GLB bytes are preserved and tested. Native Blender stills under `previews/` show
authored geometry; they are distinct from browser screenshots and traffic proof.

There is no blanket MIT/CC0 license assertion: the repository owner has not selected a license. Public availability is not equivalent to a copyright license. Local QA used separately installed Three.js and Khronos glTF Validator; their code is excluded from this asset pack.
