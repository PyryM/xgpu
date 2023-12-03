import { readFileSync, writeFileSync } from "fs";

const SRC = readFileSync("codegen/webgpu.h").toString("utf8");

interface FuncArg {
  name: string;
  explicitPointer: boolean;
  explicitConst: boolean;
  ctype: CType;
}

function emitArg(arg: FuncArg): string {
  return `${arg.ctype.cName} ${arg.explicitConst ? "const " : ""}${
    arg.explicitPointer ? "* " : ""
  }${arg.name}`;
}

interface CFunc {
  parent?: string;
  name: string;
  signature: string;
  args: FuncArg[];
  ret?: FuncArg;
}

interface CType {
  kind: "opaque" | "enum" | "primitive" | "struct";
  pyName: string;
  cName: string;
  pyAnnotation(isPointer: boolean): string;
  wrap(val: string, isPointer: boolean): string;
  unwrap(val: string, isPointer: boolean): string;
  emit?(): string;
  cdef?(): string;
  precdef?(): string;
  addFunc?(func: CFunc): void;
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

  pyAnnotation(): string {
    return this.pyName;
  }

  wrap(val: string): string {
    return `${this.pyName}(${val})`;
  }

  unwrap(val: string): string {
    return `int(${val})`;
  }

  precdef(): string {
    return `typedef uint32_t ${this.cName};`;
  }

  emit(): string {
    let frags: string[] = [`class ${this.pyName}(IntEnum):`];
    for (const { name, val } of this.values) {
      if (name !== "Force32") {
        frags.push(`    ${sanitizeIdent(name)} = ${val}`);
      }
    }
    return frags.join("\n") + "\n";
  }
}

function removePrefixCaseInsensitive(s: string, prefix: string): string {
  if (s.toLowerCase().startsWith(prefix.toLowerCase())) {
    return s.slice(prefix.length);
  } else {
    return s;
  }
}

function removePrefix(s: string, prefixes: string | string[]): string {
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

function cleanup(s: string, prefix: string): string {
  return removePrefix(s.trim(), [prefix, "_"]);
}

function parseEnumEntry(parentName: string, entry: string): CEnumVal {
  const [name, val] = entry.split("=").map((e) => e.trim());
  return { name: cleanup(name, parentName), val };
}

function recase(ident: string, upperFirst: boolean): string {
  const firstchar = ident.charAt(0);
  const target = upperFirst ? firstchar.toUpperCase() : firstchar.toLowerCase();
  return target + ident.slice(1);
}

function toPyName(ident: string, isClass = false): string {
  return recase(removePrefix(ident, ["WGPU", "wgpu"]), isClass);
}

interface Refinfo {
  nullable?: boolean;
  constant?: boolean;
  explicitPointer?: boolean;
  inner: string;
}

function parseTypeRef(ref: string): Refinfo {
  const info: Refinfo = { inner: "unknown" };
  for (const part of ref.trim().split(" ")) {
    if (part === "WGPU_NULLABLE") {
      info.nullable = true;
    } else if (part === "const") {
      info.constant = true;
    } else if (part === "*") {
      info.explicitPointer = true;
    } else {
      info.inner = part;
    }
  }
  if (
    info.inner === "WGPUChainedStruct" ||
    info.inner === "WGPUChainedStructOut"
  ) {
    // chained structs are always nullable?
    info.nullable = true;
  }
  return info;
}

function parseTypedIdent(entry: string): { name: string; type: Refinfo } {
  const matched = entry.match(/(.*) ([A-Za-z0-9_]+)$/);
  if (!matched) {
    throw new Error(`Unable to parse: "${entry}"`);
  }
  const [_wholeMatch, type, name] = matched;
  //console.log(`>>>>>>>>> ${name} >>>>>>>> "${type}"`)
  return { name, type: parseTypeRef(type) };
}

function prim(cName: string, pyName: string): CType {
  return {
    cName,
    pyName,
    kind: "primitive",
    pyAnnotation: () => pyName,
    wrap: (v) => v,
    unwrap: (v) => v,
  };
}

class ApiInfo {
  types: Map<string, CType> = new Map();
  UNKNOWN_TYPE: CType = prim("UNKNOWN", "Any");
  looseFuncs: CFunc[] = [];

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
      ["WGPUBool", "bool"],
      ["UNKNOWN", "Any"],
    ];
    for (const [cName, pyName] of PRIMITIVES) {
      this.types.set(cName, prim(cName, pyName));
    }

    this.types.set("void", {
      cName: "void",
      pyName: "VOID",
      kind: "primitive",
      pyAnnotation: (isPointer) => (isPointer ? "Any" : "None"),
      wrap: (v, isPointer) => v,
      unwrap: (v, isPointer) => v,
    });

    // C `char *` is treated specially as Python `str`
    this.types.set("char", {
      cName: "char",
      pyName: "str",
      kind: "primitive",
      pyAnnotation: (isPointer) => (isPointer ? "str" : "int"),
      wrap: (v, isPointer) => (isPointer ? `ffi.string(${v})` : v),
      unwrap: (v) => v,
    });
  }

  getType(t: Refinfo | string): CType {
    if (typeof t !== "string") {
      t = t.inner;
    }
    return this.types.get(t) ?? this.UNKNOWN_TYPE;
  }

  findEnums(src: string) {
    const enumExp = /typedef enum ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
    for (const m of src.matchAll(enumExp)) {
      const [_wholeMatch, name, body] = m;
      const entries = body
        .split(",")
        .map((e) => parseEnumEntry(name.trim(), e));
      const cName = name.trim();
      this.types.set(cName, new CEnum(cName, toPyName(cName, true), entries));
    }
  }

  findOpaquePointers(src: string) {
    const reg = /typedef struct ([a-zA-Z0-9]+)\* ([a-zA-Z]+)([^;]*);/g;
    for (const m of src.matchAll(reg)) {
      const [_wholeMatch, _implName, cName, _extra] = m;
      this.types.set(cName, new COpaque(cName, toPyName(cName, true)));
    }
  }

  _createField(name: string, ref: Refinfo): CStructField {
    const type = this.getType(ref);
    if (
      ref.explicitPointer ||
      type.kind === "opaque" ||
      type.kind === "struct"
    ) {
      return new PointerField(name, type, ref.nullable ?? false);
    } else {
      return new ValueField(name, type);
    }
  }

  _addStruct(cdef: string, cName: string, body: string) {
    const rawFields: { name: string; type: Refinfo }[] = [];
    for (const line of body.split(";")) {
      if (line.trim().length > 0) {
        rawFields.push(parseTypedIdent(line.trim()));
      }
    }
    const fields: CStructField[] = [];
    let fieldPos = 0;
    while (fieldPos < rawFields.length) {
      const { name, type } = rawFields[fieldPos];
      if (
        name.endsWith("Count") &&
        type.inner === "size_t" &&
        fieldPos + 1 < rawFields.length
      ) {
        const { name: arrName, type: arrType } = rawFields[fieldPos + 1];
        fields.push(new ArrayField(arrName, name, this.getType(arrType)));
        fieldPos += 2;
      } else {
        fields.push(this._createField(name, type));
        ++fieldPos;
      }
    }
    this.types.set(
      cName,
      new CStruct(cName, toPyName(cName, true), cdef, fields)
    );
  }

  findConcreteStructs(src: string) {
    const reg = /typedef struct ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
    for (const m of src.matchAll(reg)) {
      const [cdef, name, rawBody] = m;
      this._addStruct(cdef, name, rawBody);
    }
  }

  _findFuncParent(args: FuncArg[]): CType | undefined {
    if (args.length > 0) {
      const thisType = args[0].ctype.cName;
      return this.types.get(thisType);
    }
    return undefined;
  }

  _parseFuncReturn(returnType: string): FuncArg {
    if (returnType === "void") {
      return {
        name: "return",
        ctype: this.getType("void"),
        explicitConst: false,
        explicitPointer: false,
      };
    } else {
      const info = parseTypeRef(returnType);
      return {
        name: "return",
        ctype: this.getType(info),
        explicitConst: info.constant === true,
        explicitPointer: info.explicitPointer === true,
      };
    }
  }

  _parseFuncArgs(argStr: string): FuncArg[] {
    return argStr.split(",").map((ident) => {
      let { name, type } = parseTypedIdent(ident);
      return {
        name,
        ctype: this.getType(type),
        explicitPointer: type.explicitPointer === true,
        explicitConst: type.constant === true,
      };
    });
  }

  _addFunc(name: string, argStr: string, returnType: string) {
    const args = this._parseFuncArgs(argStr);
    const ret = this._parseFuncReturn(returnType);

    const signature = `${returnType} ${name}(${args})`;
    let func: CFunc = { name, signature, args, ret };

    const parent = this._findFuncParent(args);
    if (parent !== undefined && parent.addFunc) {
      parent.addFunc(func);
    } else {
      console.log(`Couldn't find parent for ${name}`);
      this.looseFuncs.push(func);
    }
  }

  _addCallbackType(name: string, argStr: string, returnType: string) {
    console.log(`Callback: ${name}(${argStr}) -> ${returnType}`);
    const args = this._parseFuncArgs(argStr);
    const ret = this._parseFuncReturn(returnType);

    this.types.set(name, new CFuncPointer(name, toPyName(name), args, ret));
  }

  findCallbackTypes(src: string) {
    // typedef void (*WGPUBufferMapCallback)(WGPUBufferMapAsyncStatus status, void * userdata) WGPU_FUNCTION_ATTRIBUTE;
    const reg =
      /typedef (.*) \(\*([A-Za-z0-9]+)\)\((.*)\) WGPU_FUNCTION_ATTRIBUTE;/g;
    for (const m of src.matchAll(reg)) {
      const [_wholeMatch, returnType, name, args] = m;
      if (!name.endsWith("Callback")) {
        continue;
      }
      this._addCallbackType(name, args, returnType);
    }
  }

  findExportedFunctions(src: string) {
    const reg =
      /WGPU_EXPORT (.*) ([a-zA-Z0-9_]+)\((.*)\) WGPU_FUNCTION_ATTRIBUTE;/g;
    for (const m of src.matchAll(reg)) {
      const [_wholeMatch, returnType, name, args] = m;
      this._addFunc(name, args, returnType);
    }
  }

  parse(src: string) {
    this.findEnums(src);
    this.findOpaquePointers(src);
    this.findConcreteStructs(src);
    this.findCallbackTypes(src);
    this.findExportedFunctions(src);
  }
}

class CFuncPointer implements CType {
  kind: "opaque" = "opaque";

  constructor(
    public cName: string,
    public pyName: string,
    public args: FuncArg[],
    public ret: FuncArg
  ) {}

  pyAnnotation(): string {
    const arglist = this.args.map((arg) => {
      if (arg.ctype.kind === "primitive") {
        return arg.ctype.pyAnnotation(arg.explicitPointer);
      } else if (arg.ctype.kind === "enum") {
        return "int";
      } else {
        // TODO: consider wrapping python callbacks?
        return "Any";
      }
    });
    return `Callable[[${arglist}], ${this.ret.ctype.pyAnnotation(
      this.ret.explicitPointer
    )}]`;
  }

  wrap(val: string): string {
    return val;
  }

  unwrap(val: string): string {
    return val;
  }

  // emit?(): string {
  //   throw new Error("Method not implemented.");
  // }

  precdef?(): string {
    const args = this.args.map(emitArg).join(", ");
    return `typedef ${this.ret.ctype.cName} (*${this.cName})(${args});`;
  }
}

interface CStructField {
  name: string;
  ctype: CType;
  prop(): string;
  arg(): string;
}

class ArrayField implements CStructField {
  constructor(
    public name: string,
    public countName: string,
    public ctype: CType
  ) {}

  arg(): string {
    return `${this.name}: list[${this.ctype.pyName}]`;
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
        ptr_arr[idx] = ${this.ctype.unwrap("item", false)}
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

function pyOptional(pyType: string): string {
  // return `Optional[${pyType}]`
  return `${pyType} | None`;
}

class PointerField implements CStructField {
  constructor(
    public name: string,
    public ctype: CType,
    public nullable: boolean
  ) {}

  argtype(): string {
    return this.nullable ? pyOptional(this.ctype.pyName) : this.ctype.pyName;
  }

  arg(): string {
    return `${this.name}: ${this.argtype()}`;
  }

  setterBody(): string[] {
    const unwrapped = this.ctype.unwrap("v", true);
    if (this.nullable && unwrapped !== "v") {
      // slight optimization: if unwrap(v) is just v then skip
      // the none check because we can just directly assign
      return [
        `self._${this.name} = v`,
        `if v is None:`,
        `    self._cdata.${this.name} = None`,
        `else:`,
        `    self._cdata.${this.name} = ${unwrapped}`,
      ];
    } else {
      return [
        `self._${this.name} = v`,
        `self._cdata.${this.name} = ${unwrapped}`,
      ];
    }
  }

  prop(): string {
    return `
@property
def ${this.name}(self) -> ${this.argtype()}:
    return self._${this.name}

@${this.name}.setter
def ${this.name}(self, v: ${this.argtype()}):
${indent(1, this.setterBody())}`;
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
  kind: "opaque" = "opaque";
  funcs: CFunc[] = [];

  constructor(public cName: string, public pyName: string) {}

  pyAnnotation(): string {
    return `"${this.pyName}"`;
  }

  wrap(val: string): string {
    return `${this.pyName}(${val})`;
  }

  unwrap(val: string): string {
    return `${val}._cdata`;
  }

  precdef(): string {
    return `typedef struct ${this.cName}Impl* ${this.cName};`;
  }

  addFunc(func: CFunc): void {
    console.log(`Adding ${func.name} to ${this.cName}`);
    this.funcs.push(func);
  }

  emitFunc(func: CFunc): string {
    const pyArglist = [
      "self",
      ...func.args
        .slice(1)
        .map(
          (arg) => `${arg.name}: ${arg.ctype.pyAnnotation(arg.explicitPointer)}`
        ),
    ];
    const callArglist = [
      "self._cdata",
      ...func.args
        .slice(1)
        .map((arg) => arg.ctype.unwrap(arg.name, arg.explicitPointer)),
    ];
    const retval =
      func.ret !== undefined
        ? ` -> ${func.ret.ctype.pyAnnotation(func.ret.explicitPointer)}`
        : "";
    const fname = toPyName(removePrefixCaseInsensitive(func.name, this.cName));

    return `
    def ${fname}(${pyArglist.join(", ")})${retval}:
        return lib.${func.name}(${callArglist.join(", ")})`;
  }

  emit(): string {
    return `
class ${this.pyName}:
    def __init__(self, cdata):
        self._cdata = cdata
${this.funcs.map((f) => this.emitFunc(f)).join("\n")}
`;
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

  pyAnnotation(): string {
    return `"${this.pyName}"`;
  }

  wrap(val: string): string {
    return `raise ValueError("This property cannot be queried!")`;
  }

  unwrap(val: string): string {
    return `${val}._cdata`;
  }

  precdef(): string {
    return `struct ${this.cName};`;
  }

  cdef(): string {
    return `${this._cdef} ${this.cName};`;
  }

  emit(): string {
    return `
class ${this.pyName}:
    def __init__(self, *, ${this.fields.map((f) => f.arg()).join(", ")}):
        self._cdata = ${ffiNew(this.cName)}
${indent(
  2,
  this.fields.map((f) => `self.${f.name} = ${f.name}`)
)}
${this.fields.map((f) => indent(1, f.prop())).join("\n")}
`;
  }
}

// TODO/THOUGHTS:
// * a small number of structs need to be mutated
//   (e.g., limits structs which are mutated to return limits)
// * horrible chained struct stuff
// * bitflags: take in set[enum] or list[enum] or sequence[enum]?
// * refcounting `reference`, `release`: ffi.gc on CDATA wrap ?
// * default arguments? maybe better to not have any defaults!

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

const finalOutput = `# AUTOGENERATED
from collections.abc import Callable
from enum import IntEnum
from typing import Any

from cffi import FFI

ffi = FFI()
# TODO: figure out DLL name on different platforms!
lib = ffi.dlopen("wgpu-native.dll")

ffi.cdef("""
typedef uint32_t WGPUFlags;
typedef uint32_t WGPUBool;

${predefFrags.join("\n")}

${cdefFrags.join("\n")}
""")

${pyFrags.join("\n")}
`;

writeFileSync("webgoo.py", finalOutput);
