import { readFileSync } from "fs";

const SRC = readFileSync("codegen/webgpu.h").toString("utf8");

interface CType {
  opaque: boolean;
  pointer: boolean;
  primitive: boolean;
  pyName: string;
  cName: string;
  wrap(val: string): string;
  unwrap(val: string): string;
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
  opaque: boolean = false;
  pointer: boolean = false;
  primitive: boolean = true;

  constructor(public cName: string, public pyName: string, public values: CEnumVal[]){}

  wrap(val: string): string {
    return `${this.pyName}(${val})`
  }

  unwrap(val: string): string {
    return `int(val)`
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

function findEnums(src: string): CEnum[] {
  let res: CEnum[] = [];

  const enumExp = /typedef enum ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
  for (const m of src.matchAll(enumExp)) {
    const [_wholeMatch, name, body] = m;
    const entries = body.split(",").map((e) => parseEnumEntry(name.trim(), e));
    res.push(new CEnum(name.trim(), pyName(name.trim()),  entries));
  }

  return res;
}

type TypeInfo =
  | { kind: "enum"; info: CEnum }
  | { kind: "opaque"; ctype: string }
  | { kind: "struct" }
  | { kind: "primitive"; ctype: string };

class ApiInfo {
  opaques: Set<string> = new Set();
  enums: Map<string, CEnum> = new Map();

  constructor() {}

  typeInfo(ctype: string): TypeInfo {
    const opaque = this.opaques.has(ctype);
    const enumt = this.enums.get(ctype);

    if (opaque) {
      return { kind: "opaque", ctype };
    } else if (enumt) {
      return { kind: "enum", info: enumt };
    } else {
      return { kind: "primitive", ctype };
    }
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

function findOpaquePointers(src: string): Set<string> {
  throw new Error("NYI!");
  const opaques: Set<string> = new Set();
  const reg = /typedef struct [a-zA-Z0-9]*\* /g;
  return opaques;
}

const enums = findEnums(SRC);
for (const e of enums) {
  console.log(e.emit());
  console.log("");
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

interface CStruct {
  ctype: string;
  pytype: string;
  cdefinition: string;
  fields: CStructField[];
}

function identity(v: string): string {
  return v;
}

// class Primitive implements CType {
//   opaque: boolean = false;
//   primitive: boolean = true;

//   constructor(public cName: string, public pyName: string, public pointer: boolean = false) {}

//   wrap(val: string): string {
//     if(this.)
//   }

//   unwrap(val: string): string {

//   }
// }

function prim(cName: string, pyName: string): CType {
  return {
    cName,
    pyName,
    primitive: true,
    opaque: false,
    pointer: false,
    wrap: identity,
    unwrap: identity,
  };
}

const PRIMITIVES: { [k: string]: CType } = {
  uint64_t: prim("uint64_t", "int"),
  uint32_t: prim("uint32_t", "int"),
  uint16_t: prim("uint16_t", "int"),
  uint8_t: prim("uint8_t", "int"),
  int64_t: prim("int64_t", "int"),
  int32_t: prim("int32_t", "int"),
  int16_t: prim("int16_t", "int"),
  int8_t: prim("int8_t", "int"),
  float: prim("float", "float"),
  double: prim("double", "float"),
};

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

function emitWrapperClass(cs: CStruct): string {
  return `
class ${cs.pytype}:
    def __init__(self, ${cs.fields.map((f) => f.arg()).join(", ")}):
        self._cdata = ${ffiNew(cs.ctype)}
${indent(
  2,
  cs.fields.map((f) => `self.${f.name} = ${f.name}`)
)}
  
${cs.fields.map((f) => indent(1, f.prop())).join("\n")}
`;
}

const example: CStruct = {
  cdefinition: `
typedef struct WGPUExtent3D {
  uint32_t width;
  uint32_t height;
  uint32_t depthOrArrayLayers;
} WGPUExtent3D WGPU_STRUCTURE_ATTRIBUTE;
  `,
  pytype: "Extent3D",
  ctype: "WGPUExtent3D",
  fields: [
    new ValueField("width", PRIMITIVES.uint32_t),
    new ValueField("height", PRIMITIVES.uint32_t),
    new ValueField("depthOrArrayLayers", PRIMITIVES.uint32_t),
  ],
};

console.log(emitWrapperClass(example));

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
