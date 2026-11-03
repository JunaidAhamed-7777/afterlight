/** Shared transport boundary. Schema-specific validation remains the caller's job. */
export const MAX_JSON_BYTES = 128 * 1024 * 1024;
export const MAX_JSON_DEPTH = 64;

export function parseJsonBytes(bytes: Uint8Array): unknown {
  if (bytes.byteLength > MAX_JSON_BYTES)
    throw new Error("This response exceeds the supported trace size limit.");
  let text: string;
  try {
    // The default BOM handling accepts one UTF-8 BOM without changing hashed bytes.
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error("This response is not valid UTF-8 JSON.");
  }
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (const character of text) {
    if (inString) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') inString = false;
    } else if (character === '"') inString = true;
    else if (character === "{" || character === "[") {
      depth += 1;
      if (depth > MAX_JSON_DEPTH)
        throw new Error(`JSON container nesting exceeds depth ${MAX_JSON_DEPTH}.`);
    } else if (character === "}" || character === "]") {
      depth -= 1;
      if (depth < 0) throw new Error("This response has malformed JSON container nesting.");
    }
  }
  // Native parsing still rejects malformed syntax, strings and non-JSON tokens.
  const value: unknown = JSON.parse(text);
  // JSON.parse accepts exponent overflow. Visit every value without recursion or
  // copying large arrays, including extras not consumed by schema validators.
  const pending: Iterator<unknown>[] = [[value][Symbol.iterator]()];
  while (pending.length) {
    const next = pending[pending.length - 1].next();
    if (next.done) { pending.pop(); continue; }
    const item = next.value;
    if (typeof item === "number" && !Number.isFinite(item))
      throw new Error("This response contains a nonfinite JSON number.");
    if (Array.isArray(item)) pending.push(item[Symbol.iterator]());
    else if (item !== null && typeof item === "object") {
      const object = item as Record<string, unknown>;
      const keys = Object.keys(object)[Symbol.iterator]();
      pending.push({ next() {
        const key = keys.next();
        return key.done ? { done: true, value: undefined } : { done: false, value: object[key.value] };
      } });
    }
  }
  return value;
}
