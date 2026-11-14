/** Read retained JSON for display while preserving every original number token. */
export function displayJson(raw: string): unknown {
  let transformed = "";
  let quoted = false;
  let escaped = false;
  for (let index = 0; index < raw.length; index++) {
    const character = raw[index];
    if (quoted) {
      transformed += character;
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') quoted = false;
    } else if (character === '"') {
      quoted = true;
      transformed += character;
    } else if (character === "-" || /[0-9]/.test(character)) {
      const token = raw.slice(index).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/);
      if (!token) throw new Error("Invalid retained JSON number token");
      transformed += JSON.stringify(token[0]);
      index += token[0].length - 1;
    } else transformed += character;
  }
  return JSON.parse(transformed) as unknown;
}

export function objectValue(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}
