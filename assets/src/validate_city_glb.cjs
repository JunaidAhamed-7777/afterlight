/* Run the official Khronos validator installed locally; no dependency copying.
 * node assets/src/validate_city_glb.cjs C:/path/to/node_modules/gltf-validator
 */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const validator = require(path.resolve(process.argv[2] || "node_modules/gltf-validator"));
const root = path.resolve(__dirname, "..");
const input = path.join(root, "exports/city_enhanced.glb");
const bytes = fs.readFileSync(input);
validator.validateBytes(new Uint8Array(bytes), {
  uri: "city_enhanced.glb", format: "glb", maxIssues: 1000, writeTimestamp: false,
  externalResourceFunction: uri => Promise.reject(new Error("External asset URI: " + uri)),
}).then(report => {
  const result = {schema: "afterlight.city-gltf-audit.v1", validator: "Khronos glTF Validator",
    version: validator.version(), asset_sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    asset_bytes: bytes.length, ...report};
  fs.writeFileSync(path.join(root, "qa/city_expanded_gltf_audit.json"), JSON.stringify(result, null, 2)+"\n");
  console.log(JSON.stringify({version:result.version, bytes:bytes.length, issues:report.issues, info:report.info}));
  if (report.issues.numErrors || report.issues.numWarnings) process.exitCode = 1;
}).catch(error => { console.error(error); process.exitCode=1; });
