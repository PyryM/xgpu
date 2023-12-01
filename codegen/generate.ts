import { readFileSync, writeFileSync } from "fs";

const SRC = readFileSync("codegen/webgpu.h").toString("utf8");

interface CType {
  kind: "opaque" | "enum" | "primitive" | "struct";
  pyName: string;
  cName: string;
  wrap(val: string): string;
  unwrap(val: string): string;
  emit?(): string;
  cdef?(): string
  precdef?(): string
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
    return `int(${val})`;
  }

  precdef(): string {
    return `typedef uint32_t ${this.cName};`
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

interface Refinfo {
  nullable?: boolean
  constant?: boolean
  explicitPointer?: boolean
  inner: string
}

function parseTypeRef(ref: string): Refinfo {
  const info: Refinfo = {inner: "unknown"}
  for(const part of ref.trim().split(" ")) {
    if(part === "WGPU_NULLABLE") {
      info.nullable = true
    } else if(part === "const") {
      info.constant = true
    } else if(part === "*") {
      info.explicitPointer = true
    } else {
      info.inner = part
    }
  }
  return info
}

function canonicalName(ref: Refinfo): string {
  if(ref.explicitPointer && ref.inner === "char") {
    // special case for strings?
    return "cstr"
  } else {
    return ref.inner
  }
}

function parseStructEntry(entry: string): {name: string, type: Refinfo} {
  const matched = entry.match(/(.*) ([A-Za-z0-9_]+)$/);
  if (!matched) {
    throw new Error(`Unable to parse: "${entry}"`);
  }
  const [_wholeMatch, type, name] = matched;
  //console.log(`>>>>>>>>> ${name} >>>>>>>> "${type}"`)
  return { name, type: parseTypeRef(type) };
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
      ["size_t", "int"],
      ["ERROR", "int"],
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

    this.types.set("cstr", {
      cName: "const char *",
      pyName: "str",
      kind: "primitive",
      wrap: (v) => `ffi.string(${v})`,
      unwrap: (v) => v,
    })
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
      this.types.set(cName, new COpaque(cName, cName));
    }
  }

  _createField(name: string, ref: Refinfo): CStructField {
    const ctype = canonicalName(ref);
    const type = this.types.get(ctype) ?? this.types.get("ERROR")!;
    if(ref.explicitPointer || type.kind === "opaque" || type.kind === "struct") {
      return new PointerField(name, type, ref.nullable ?? false)
    } else {
      return new ValueField(name, type)
    }
  }

  _createArrayField(countField: string, arrField: string, arrType: Refinfo): CStructField {
    const ctype = canonicalName(arrType);
    const type = this.types.get(ctype) ?? this.types.get("ERROR")!;
    return new ArrayField(arrField, countField, type);
  }

  _addStruct(cdef: string, cName: string, body: string) {
    const rawFields: {name: string, type: Refinfo}[] = [];
    for (const line of body.split(";")) {
      if (line.trim().length > 0) {
        rawFields.push(parseStructEntry(line.trim()));
      }
    }
    const fields: CStructField[] = [];
    let fieldPos = 0;
    while(fieldPos < rawFields.length) {
      const {name, type} = rawFields[fieldPos];
      if(name.endsWith("Count") && type.inner === "size_t" && (fieldPos + 1 < rawFields.length)) {
        const {name: arrName, type: arrType} = rawFields[fieldPos+1];
        fields.push(this._createArrayField(name, arrName, arrType));
        fieldPos += 2;
      } else {
        fields.push(this._createField(name, type));
        ++fieldPos;
      }
    }
    this.types.set(cName, new CStruct(cName, pyName(cName), cdef, fields));
  }

  findConcreteStructs(src: string) {
    const reg = /typedef struct ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
    for (const m of src.matchAll(reg)) {
      const [cdef, name, rawBody] = m;
      this._addStruct(cdef, name, rawBody);
    }
  }

  parse(src: string) {
    this.findOpaquePointers(src);
    this.findEnums(src);
    this.findConcreteStructs(src);
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

interface CStructField {
  name: string;
  ctype: CType;
  prop(): string;
  arg(): string;
}

class ArrayField implements CStructField {
  constructor(public name: string, public countName: string, public ctype: CType) {}

  arg(): string {
    return `${this.name}: list[${this.ctype.pyName}]`
  }

  prop(): string {
    return `
@property
def ${this.name}(self) -> list[${this.ctype.pyName}]:
    return self._${this.name}

@${this.name}.setter
def ${this.name}(self, v: list[${this.ctype.pyName}]):
    count = len(v)
    ptr_arr = ffi.new('${this.ctype.cName}[]', count)
    for idx, item in enumerate(v):
        ptr_arr[idx] = ${this.ctype.unwrap("item")}
    self._${this.name} = v
    self._${this.name}_arr = ptr_arr
    self._cdata.${this.countName} = count
    self._cdata.${this.name} = ptr_arr`;
  }
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
  constructor(public name: string, public ctype: CType, public nullable: boolean) {}

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

class COpaque implements CType {
  kind: "opaque" = "opaque"

  constructor(
    public cName: string,
    public pyName: string
  ) {}

  wrap(val: string): string {
    return `${this.pyName}(${val})`
  }

  unwrap(val: string): string {
    return `${val}._cdata`
  }

  precdef(): string {
    return `typedef struct ${this.cName}Impl* ${this.cName};`
  }

  emit(): string {
    return `
class ${this.pyName}:
    def __init__(self, cdata):
        self._cdata = cdata
`
  }
}

class CStruct implements CType {
  kind: "struct" = "struct";

  constructor(
    public cName: string,
    public pyName: string,
    public _cdef: string,
    public fields: CStructField[]
  ) {}

  wrap(val: string): string {
    return `raise ValueError("This property cannot be queried!")`
  }

  unwrap(val: string): string {
    return `${val}._cdata`;
  }

  precdef(): string {
    return `struct ${this.cName};`
  }

  cdef(): string {
    return `${this._cdef} ${this.cName};`
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

// const uint32 = api.types.get("uint32_t")!;

// const example = new CStruct(
//   "WGPUExtent3D",
//   "Extent3D",
//   `
// typedef struct WGPUExtent3D {
//   uint32_t width;
//   uint32_t height;
//   uint32_t depthOrArrayLayers;
// } WGPUExtent3D WGPU_STRUCTURE_ATTRIBUTE;
//   `,
//   [
//     new ValueField("width", uint32),
//     new ValueField("height", uint32),
//     new ValueField("depthOrArrayLayers", uint32),
//   ]
// );

// console.log(example.emit());

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
// * horrible chained struct stuff

const api = new ApiInfo();
api.parse(SRC);

const predefFrags: string[] = [];
const cdefFrags: string[] = [];
const pyFrags: string[] = [];

for (const [name, ctype] of api.types.entries()) {
  if (ctype.precdef) {
    predefFrags.push(ctype.precdef());
  }

  if (ctype.cdef) {
    cdefFrags.push(ctype.cdef());
  }

  if (ctype.emit) {
    pyFrags.push(ctype.emit());
  }
}

const finalOutput = `
from enum import IntEnum
from cffi import FFI

ffi = FFI()
ffi.cdef("""
typedef uint32_t WGPUFlags;
typedef uint32_t WGPUBool;

${predefFrags.join("\n")}

${cdefFrags.join("\n")}
""")

${pyFrags.join("\n")}
`

writeFileSync("webgoo.py", finalOutput)