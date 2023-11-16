import { readFileSync } from "fs";

console.log("Hello via Bun!");

const SRC = readFileSync("codegen/webgpu.h").toString("utf8");

interface CEnumVal {
  name: string;
  val: string;
}

interface CEnum {
  name: string;
  entries: CEnumVal[];
}

function removePrefix(s: string, prefix: string): string {
  if (s.startsWith(prefix)) {
    s = s.slice(prefix.length);
  }
  return s;
}

function cleanup(s: string, prefix: string): string {
  s = s.trim();
  s = removePrefix(s, prefix);
  s = removePrefix(s, "_");
  return s;
}

function parseEnumEntry(parentName: string, entry: string): CEnumVal {
  const [name, val] = entry.split("=").map((e) => e.trim());
  return { name: cleanup(name, parentName), val };
}

function findEnums(src: string): CEnum[] {
  let res: CEnum[] = [];

  const enumExp = /typedef enum ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
  for (const m of src.matchAll(enumExp)) {
    const [_wholeMatch, name, body] = m;
    const entries = body.split(",").map((e) => parseEnumEntry(name.trim(), e));
    res.push({ name: name.trim(), entries });
  }

  return res;
}

function pyName(ident: string): string {
  return removePrefix(ident, "WGPU");
}

function sanitizeIdent(ident: string): string {
  if (!ident.match(/^[a-zA-Z]/) || ident === "None") {
    ident = "_" + ident;
  }
  return ident;
}

function emitEnum(src: CEnum): string {
  let frags: string[] = [`class ${pyName(src.name)}(IntEnum):`];
  for (const { name, val } of src.entries) {
    frags.push(`    ${sanitizeIdent(name)} = ${val}`);
  }
  return frags.join("\n");
}

const EXAMPLE = `
typedef struct WGPUAdapterImpl* WGPUAdapter WGPU_OBJECT_ATTRIBUTE;
typedef struct WGPUBindGroupImpl* WGPUBindGroup WGPU_OBJECT_ATTRIBUTE;
typedef struct WGPUBindGroupLayoutImpl* WGPUBindGroupLayout WGPU_OBJECT_ATTRIBUTE;
typedef struct WGPUBufferImpl* WGPUBuffer WGPU_OBJECT_ATTRIBUTE;
typedef struct WGPUCommandBufferImpl* WGPUCommandBuffer WGPU_OBJECT_ATTRIBUTE;
typedef struct WGPUCommandEncoderImpl* WGPUCommandEncoder WGPU_OBJECT_ATTRIBUTE;

typedef struct WGPUAdapterProperties {
    WGPUChainedStructOut * nextInChain;
    uint32_t vendorID;
    char const * vendorName;
    char const * architecture;
    uint32_t deviceID;
    char const * name;
    char const * driverDescription;
    WGPUAdapterType adapterType;
    WGPUBackendType backendType;
} WGPUAdapterProperties WGPU_STRUCTURE_ATTRIBUTE;

typedef struct WGPUBindGroupEntry {
    WGPUChainedStruct const * nextInChain;
    uint32_t binding;
    WGPU_NULLABLE WGPUBuffer buffer;
    uint64_t offset;
    uint64_t size;
    WGPU_NULLABLE WGPUSampler sampler;
    WGPU_NULLABLE WGPUTextureView textureView;
} WGPUBindGroupEntry WGPU_STRUCTURE_ATTRIBUTE;
`;

interface CStructEntry {
  name: string;
  type: string;
}

interface CStruct {
  name: string;
  rawBody: string;
  entries: CStructEntry[]
}

function parseStructEntry(entry: string): CStructEntry {
  const matched = entry.match(/(.*) ([A-Za-z0-9_]+)$/);
  if(!matched) {
    throw new Error(`Unable to parse: "${entry}"`);
  }
  const [_wholeMatch, type, name] = matched;
  return {name, type}
}

function findConcreteStructs(src: string): CStruct[] {
  const res: CStruct[] = [];
  const reg = /typedef struct ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
  for (const m of src.matchAll(reg)) {
    const [_wholeMatch, name, rawBody] = m;
    const entries: CStructEntry[] = [];
    for(const line of rawBody.split(";")) {
      if(line.trim().length > 0) {
        entries.push(parseStructEntry(line.trim()));
      }
    }
    res.push({ name: name.trim(), rawBody, entries });
  }
  return res;
}

function findOpaquePointers(src: string): Set<string> {
  throw new Error("NYI!");
  const opaques: Set<string> = new Set();
  const reg = /typedef struct [a-zA-Z0-9]*\* /g;
  return opaques;
}

// const enums = findEnums(SRC);
// for (const e of enums) {
//   console.log(emitEnum(e));
//   console.log("");
// }

const structs = findConcreteStructs(SRC);
for (const s of structs) {
  console.log(s.name);
  console.log(s.entries.map((e) => `[${e.name}] [${e.type}]`).join("\n"))
}

// TODO/THOUGHTS:
// * most structs should become classes that are effectively
//   immutable after construction (have inner .cdata)
// * ALT: just map everything with getters/setters into cdata mutations?
//   getting/setting will incur some overhead, but will maybe support
//   some patterns people might want to use?
// * a small number of structs need to be mutated
//   (e.g., limits structs which are mutated to return limits)
// * a few structs have count - then - array constructions, should
//   handle passing these as actual arrays