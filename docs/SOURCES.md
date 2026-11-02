# Source register

Research snapshot: 2 November 2026. Primary sources support rules and technical behavior; design decisions remain our proposals. Recheck mutable pages before implementation/submission. No winner or performance claim is inferred merely from a search snippet.

## Contest and historical context

- [Neural Storm home](https://neuralstorm.devpost.com/) — organizer event identity and overview.
- [Rules](https://neuralstorm.devpost.com/rules) — eligibility, permitted work, judging and submission requirements.
- [Dates](https://neuralstorm.devpost.com/details/dates) — build and submission window.
- [Resources](https://neuralstorm.devpost.com/resources) — problem statements and participant guidance.
- [ACE Hack Fest 2020](https://www.aceec.ac.in/collegeevent/hack-fest-2020-a-36-hour-national-level-students-hackathon/) — related historical winners, not the same competition/jury.
- [JNTUH achievements](https://jntuh.ac.in/directorate/achivements/14) — related institutional context; insufficient project detail for a winner blueprint.

## Simulator and evaluation

- [SUMO emergency vehicles](https://sumo.dlr.de/docs/Simulation/Emergency.html) — emergency privileges and bluelight behavior.
- [Traffic lights](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html) — phases and signal control.
- [TripInfo](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html) — trip metrics and unfinished trips.
- [Statistics output](https://sumo.dlr.de/docs/Simulation/Output/StatisticOutput.html) — inserted/running/waiting vehicle accounting.
- [Save and load](https://sumo.dlr.de/docs/Simulation/SaveAndLoad.html) — snapshot limitations and RNG/future-route considerations.
- [Downloads](https://eclipse.dev/sumo/docs/Downloads.html) and [licenses](https://eclipse.dev/sumo/docs/Libraries_Licenses.html) — installation and dependency licensing.

## Rendering and hosting

- [Blender glTF export](https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html) — supported material/geometry transfer.
- [MCP for Blender upstream](https://github.com/ahujasid/mcp-for-blender) — third-party bridge, current installation/security/telemetry documentation; pin exact revision before use.
- [Cloudflare Pages pricing](https://developers.cloudflare.com/pages/functions/pricing/) — static versus Functions billing boundary.
- [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/) — individual asset limits and deployment constraints.
- [ONNX Runtime Web](https://onnxruntime.ai/docs/get-started/with-javascript/web.html) — optional browser inference; not required for MVP.

## Evidence standard

Record source revision/version when installing software, and capture the contest rules checked at submission. “No previous same-organizer winners verified” is a research limitation, not proof none exist. No third-party asset is licensed merely because it can be downloaded.

## Additional pass 3 primary references

- [SUMO randomness](https://sumo.dlr.de/docs/Simulation/Randomness.html) — reproducibility qualifications.
- [scikit-learn pitfalls](https://scikit-learn.org/stable/common_pitfalls.html) and [cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html) — leakage and group-aware splits.
- [SUMO coordinates](https://sumo.dlr.de/docs/Geo-Coordinates.html), [vehicle values](https://sumo.dlr.de/docs/TraCI/Vehicle_Value_Retrieval.html), [FCD](https://sumo.dlr.de/docs/Simulation/Output/FCDOutput.html) — coordinate, bumper, heading and time semantics.
- [glTF specification](https://github.com/KhronosGroup/glTF/blob/main/specification/2.0/Specification.adoc) — axes/units.
- [GLTFLoader](https://threejs.org/docs/pages/GLTFLoader.html), [InstancedMesh](https://threejs.org/docs/pages/InstancedMesh.html), [color management](https://threejs.org/manual/pages/color-management.html) — target runtime behavior.
- [glTF Validator](https://github.com/KhronosGroup/glTF-Validator) — export validation, complemented by browser checks.

Registration totals are not submitted-team counts. No competition-size or easy-win claim is made here. The public repository has no license grant implied by visibility; choose and add a license deliberately before asserting open-source licensing.

## Implementation dependencies

The application uses React, React DOM, Three.js, Vite and TypeScript; exact versions are in `web/package.json` and `web/package-lock.json`. These are third-party libraries, not original project code. Original Blender geometry and canonical map remain project-authored. Python simulation uses official Eclipse SUMO, TraCI and sumolib 1.28.0, pinned together in `requirements-sim.txt`: https://pypi.org/project/eclipse-sumo/1.28.0/ . No API keys or paid hosted simulation are required. Optional scikit-learn fitting is not evidence of a trained model or measured learning benefit. Preserve dependency licenses in distributed builds; project asset/source licensing remains an owner decision.
