/** Bound decoded response bytes while streaming, even without Content-Length. */
export async function boundedBytes(response: Response, limit = 64 * 1024 * 1024): Promise<Uint8Array<ArrayBuffer>> {
  const tooLarge = () => new Error("This response exceeds the supported trace size limit.");
  if (Number(response.headers.get("Content-Length")) > limit) {
    await response.body?.cancel();
    throw tooLarge();
  }
  if (!response.body) return new Uint8Array(0);
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel();
        throw tooLarge();
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}
export async function boundedJson(response: Response): Promise<unknown> {
  return JSON.parse(new TextDecoder().decode(await boundedBytes(response)));
}
