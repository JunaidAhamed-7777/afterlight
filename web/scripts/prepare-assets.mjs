import { cp, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const root = new URL("../../", import.meta.url);
const target = new URL("../public/assets/", import.meta.url);
await mkdir(target, { recursive: true });
for (const path of [
  "exports",
  "map/city_manifest.json",
  "previews/city_overview.png",
]) {
  await cp(new URL(`assets/${path}`, root), new URL(path, target), {
    recursive: true,
  });
}
console.log(`Prepared original assets in ${fileURLToPath(target)}`);
