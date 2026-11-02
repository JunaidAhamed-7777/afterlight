import type { CatalogEntry } from "./types.ts";
export function recordingUrl(value: string, catalogBase: string): string {
  const base = new URL(catalogBase);
  const url = new URL(value, base);
  if (
    url.origin !== base.origin ||
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password
  )
    throw new Error(
      "Recording links must stay on the configured library origin.",
    );
  return url.href;
}
export function validateCatalog(
  value: unknown,
  catalogBase: string,
): CatalogEntry[] {
  const catalog = value as { schema?: unknown; runs?: unknown };
  if (
    catalog?.schema !== "afterlight.catalog.v1" ||
    !Array.isArray(catalog.runs)
  )
    throw new Error("The recording catalog has an unsupported format.");
  const ids = new Set<string>();
  return catalog.runs.map((row: unknown) => {
    const r = row as CatalogEntry;
    if (
      !r ||
      !["id", "title", "url", "pickup_id", "hospital_id", "policy"].every(
        (key) =>
          typeof r[key as keyof CatalogEntry] === "string" &&
          String(r[key as keyof CatalogEntry]).trim(),
      ) ||
      ids.has(r.id) ||
      !Number.isInteger(r.seed) ||
      !Number.isFinite(r.duration_s) ||
      r.duration_s <= 0
    )
      throw new Error(
        "The recording catalog contains incomplete or duplicate entries.",
      );
    recordingUrl(r.url, catalogBase);
    ids.add(r.id);
    return r;
  });
}
