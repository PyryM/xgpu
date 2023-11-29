import { readFileSync } from "fs";

const SRC = readFileSync("codegen/webgpu.h").toString("utf8");

interface CType {
  kind: "opaque" | "enum" | "primitive" | "struct";
  pyName: string;
  cName: string;
  wrap(val: string): string;
  unwrap(val: string): string;
  emit?(): string;
}

interface CEnumVal {
  name: string;
  val: string;
}

function sanitizeIdent(ident: string): string {
  if (!ident.match(/^[a-zA-Z]/) || ident === "None") {
    ident = "_" + ident;
  }
  return ident;
}

class CEnum implements CType {
  kind: "enum" = "enum";

  constructor(
    public cName: string,
    public pyName: string,
    public values: CEnumVal[]
  ) {}

  wrap(val: string): string {
    return `${this.pyName}(${val})`;
  }

  unwrap(val: string): string {
    return `int(val)`;
  }

  emit(): string {
    let frags: string[] = [`class ${this.pyName}(IntEnum):`];
    for (const { name, val } of this.values) {
      frags.push(`    ${sanitizeIdent(name)} = ${val}`);
    }
    return frags.join("\n");
  }
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

function pyName(ident: string): string {
  return removePrefix(ident, "WGPU");
}

class ApiInfo {
  types: Map<string, CType> = new Map();

  constructor() {
    const PRIMITIVES: [string, string][] = [
      ["uint64_t", "int"],
      ["uint32_t", "int"],
      ["uint16_t", "int"],
      ["uint8_t", "int"],
      ["int64_t", "int"],
      ["int32_t", "int"],
      ["int16_t", "int"],
      ["int8_t", "int"],
      ["float", "float"],
      ["double", "float"],
    ];
    for (const [cName, pyName] of PRIMITIVES) {
      this.types.set(cName, {
        cName,
        pyName,
        kind: "primitive",
        wrap: (v) => v,
        unwrap: (v) => v,
      });
    }
  }

  findEnums(src: string) {
    const enumExp = /typedef enum ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
    for (const m of src.matchAll(enumExp)) {
      const [_wholeMatch, name, body] = m;
      const entries = body
        .split(",")
        .map((e) => parseEnumEntry(name.trim(), e));
      const cName = name.trim();
      this.types.set(cName, new CEnum(cName, pyName(cName), entries));
    }
  }

  findOpaquePointers(src: string) {
    const reg = /typedef struct ([a-zA-Z0-9]+)\* ([a-zA-Z]+)([^;]*);/g;
    for (const m of src.matchAll(reg)) {
      const [_wholeMatch, _implName, cName, _extra] = m;
      this.types.set(cName, {
        cName,
        pyName: cName,
        kind: "opaque",
        wrap: (v) => v,
        unwrap: (v) => v,
        emit: () => `#opaque ${cName}`
      });
    }
  }

  parse(src: string) {
    this.findOpaquePointers(src);
    this.findEnums(src);
  }
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

interface ConcreteCStructEntry {
  name: string;
  type: string;
}

interface ConcreteCStruct {
  name: string;
  rawBody: string;
  entries: ConcreteCStructEntry[];
}

function parseStructEntry(entry: string): ConcreteCStructEntry {
  const matched = entry.match(/(.*) ([A-Za-z0-9_]+)$/);
  if (!matched) {
    throw new Error(`Unable to parse: "${entry}"`);
  }
  const [_wholeMatch, type, name] = matched;
  return { name, type };
}

function findConcreteStructs(src: string): ConcreteCStruct[] {
  const res: ConcreteCStruct[] = [];
  const reg = /typedef struct ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
  for (const m of src.matchAll(reg)) {
    const [_wholeMatch, name, rawBody] = m;
    const entries: ConcreteCStructEntry[] = [];
    for (const line of rawBody.split(";")) {
      if (line.trim().length > 0) {
        entries.push(parseStructEntry(line.trim()));
      }
    }
    res.push({ name: name.trim(), rawBody, entries });
  }
  return res;
}

const api = new ApiInfo();
api.parse(SRC);
for (const [name, ctype] of api.types.entries()) {
  if (ctype.emit) {
    console.log(ctype.emit());
    console.log("");
  }
}

const structs = findConcreteStructs(SRC);
for (const s of structs) {
  console.log(s.name);
  console.log(s.entries.map((e) => `[${e.name}] [${e.type}]`).join("\n"));
}

interface CStructField {
  name: string;
  ctype: CType;
  prop(): string;
  arg(): string;
}

class ValueField implements CStructField {
  constructor(public name: string, public ctype: CType) {}

  arg(): string {
    return `${this.name}: ${this.ctype.pyName}`;
  }

  prop(): string {
    return `
@property
def ${this.name}(self) -> ${this.ctype.pyName}:
    return self._cdata.${this.name}

@${this.name}.setter
def ${this.name}(self, v: ${this.ctype.pyName}):
    self._cdata.${this.name} = v`;
  }
}

class PointerField implements CStructField {
  constructor(public name: string, public ctype: CType) {}

  arg(): string {
    return `${this.name}: ${this.ctype.pyName}`;
  }

  prop(): string {
    return `
@property
def ${this.name}(self) -> ${this.ctype.pyName}:
    return self._${this.name}

@${this.name}.setter
def ${this.name}(self, v: ${this.ctype.pyName}):
    self._${this.name} = v
    self._cdata.${this.name} = ${this.ctype.unwrap("v")}`;
  }
}

function indent(n: number, lines: string | string[]): string {
  if (typeof lines === "string") {
    lines = lines.replaceAll("\r", "").split("\n");
  }
  return lines.map((l) => `${" ".repeat(4 * n)}${l}`).join("\n");
}

function ptrTo(ctype: string): string {
  return `${ctype} *`;
}

function ffiNew(ctype: string): string {
  return `ffi.new("${ptrTo(ctype)}")`;
}

class CStruct implements CType {
  kind: "struct" = "struct";

  constructor(
    public cName: string,
    public pyName: string,
    public cdef: string,
    public fields: CStructField[]
  ) {}

  wrap(val: string): string {
    return `${val}._cdata`;
  }

  unwrap(val: string): string {
    throw new Error(`Cannot unwrap a CStruct!`);
  }

  emit(): string {
    return `
class ${this.pyName}:
    def __init__(self, ${this.fields.map((f) => f.arg()).join(", ")}):
        self._cdata = ${ffiNew(this.cName)}
${indent(
  2,
  this.fields.map((f) => `self.${f.name} = ${f.name}`)
)}
  
${this.fields.map((f) => indent(1, f.prop())).join("\n")}
`;
  }
}

const uint32 = api.types.get("uint32_t")!;

const example = new CStruct(
  "WGPUExtent3D",
  "Extent3D",
  `
typedef struct WGPUExtent3D {
  uint32_t width;
  uint32_t height;
  uint32_t depthOrArrayLayers;
} WGPUExtent3D WGPU_STRUCTURE_ATTRIBUTE;
  `,
  [
    new ValueField("width", uint32),
    new ValueField("height", uint32),
    new ValueField("depthOrArrayLayers", uint32),
  ]
);

console.log(example.emit());

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
// * methods tacked onto opaque pointer classes! (or I guess
//   concrete structs as well...). e.g., wgpuDeviceGetLimits -> device.getLimits
