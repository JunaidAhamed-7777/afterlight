/** Orthographic fit in camera-space metres. Never assumes a desktop aspect. */
export function fitOrthographic(
  points: ReadonlyArray<readonly [number, number]>,
  viewportWidth: number,
  viewportHeight: number,
  padding = 1.18,
): { halfWidth: number; halfHeight: number } {
  if (!points.length || !points.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y)))
    throw new Error("Camera bounds must contain finite projected points.");
  if (![viewportWidth, viewportHeight, padding].every(Number.isFinite) ||
      viewportWidth <= 0 || viewportHeight <= 0 || padding < 1)
    throw new Error("Camera fitting requires a positive viewport and padding >= 1.");
  const aspect = viewportWidth / viewportHeight;
  // Bounds are relative to the camera target, so retain asymmetric extents too.
  const x = Math.max(1, ...points.map(([x]) => Math.abs(x)));
  const y = Math.max(1, ...points.map(([, y]) => Math.abs(y)));
  const halfHeight = Math.max(y, x / aspect) * padding;
  const halfWidth = halfHeight * aspect;
  if (![aspect, halfWidth, halfHeight].every(Number.isFinite) ||
      aspect <= 0 || halfWidth <= 0 || halfHeight <= 0)
    throw new Error("Camera viewport or bounds exceed supported numeric extents.");
  return { halfHeight, halfWidth };
}
