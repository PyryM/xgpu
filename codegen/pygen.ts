import { recase, removePrefix } from "./stringmanip";

export const IS_PY12 = false;


export function pyOptional(pyType: string): string {
  return IS_PY12 ? `${pyType} | None` : `Optional[${pyType}]`;
}

export function pyTuple(types: string[]): string {
  const innerList = types.join(", ")
  return IS_PY12 ? `tuple[${innerList}]` : `Tuple[${innerList}]`;
}

export function pyUnion(...args: string[]): string {
  return IS_PY12 ? args.join(" | ") : `Union[${args.join(", ")}]`;
}

export function pyList(pyType: string): string {
  return IS_PY12 ? `list[${pyType}]` : `List[${pyType}]`;
}

export function toPyName(ident: string, isClass = false): string {
  return recase(removePrefix(ident, ["WGPU", "wgpu"]), isClass);
}

export function pyBool(b?: boolean): string {
  return b ? "True" : "False";
}