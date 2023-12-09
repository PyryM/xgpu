export type ParseState = { lines: string[]; pos: number };

export function discardProcs(state: ParseState) {
  const { lines } = state;
  if (!lines[state.pos].includes("WGPU_SKIP_PROCS")) {
    throw new Error(`Discard procs called at wrong position: ${state.pos}`);
  }
  ++state.pos;
  while (state.pos < lines.length) {
    if (lines[state.pos].includes("WGPU_SKIP_PROCS")) {
      return;
    }
    ++state.pos;
  }
}

function deleteStrings(line: string, deletions: string[]): string {
  for (const substr of deletions) {
    line = line.replaceAll(substr, "");
  }
  return line;
}

export function cleanHeader(src: string, deletions: string[]): string {
  const lines = src.replaceAll("\r", "").split("\n");
  let frags: string[] = [];
  const state: ParseState = { lines, pos: 0 };
  while (state.pos < lines.length) {
    const rawline = lines[state.pos];
    const line = rawline.trim();
    if (line.includes("WGPU_SKIP_PROCS")) {
      discardProcs(state);
      ++state.pos;
      continue;
    }
    if (line.startsWith("#")) {
      // discard all directives except includes
      ++state.pos;
      continue;
    }
    if (line.includes('extern "C"')) {
      // discard extern C wrapper
      ++state.pos;
      continue;
    }
    frags.push(deleteStrings(rawline, deletions));
    ++state.pos;
  }
  // collapse big blocks of newlines
  return frags.join("\n").replaceAll(/\n[\n]+/g, "\n\n");
}

export function quoted(s: string): string {
  if (s.startsWith('"')) {
    return s;
  }
  return `"${s}"`;
}

export function sanitizeIdent(ident: string): string {
  if (!ident.match(/^[a-zA-Z]/) || ident === "None") {
    ident = "_" + ident;
  }
  return ident;
}

export function removePrefixCaseInsensitive(s: string, prefix: string): string {
  if (s.toLowerCase().startsWith(prefix.toLowerCase())) {
    return s.slice(prefix.length);
  } else {
    return s;
  }
}

export function removePrefix(s: string, prefixes: string | string[]): string {
  if (typeof prefixes === "string") {
    prefixes = [prefixes];
  }

  for (const prefix of prefixes) {
    if (s.startsWith(prefix)) {
      s = s.slice(prefix.length);
    }
  }

  return s;
}

export function cleanup(s: string, prefix: string): string {
  return removePrefix(s.trim(), [prefix, "_"]);
}

export function recase(ident: string, upperFirst: boolean): string {
  const firstchar = ident.charAt(0);
  const target = upperFirst ? firstchar.toUpperCase() : firstchar.toLowerCase();
  return target + ident.slice(1);
}

export function indent2(n: number, lines: string[]): string[] {
  return lines.map((l) => `${" ".repeat(4 * n)}${l}`);
}

export function indent(n: number, lines: string | string[]): string {
  if (typeof lines === "string") {
    lines = lines.replaceAll("\r", "").split("\n");
  }
  return indent2(n, lines).join("\n");
}
