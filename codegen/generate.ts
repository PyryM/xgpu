import { readFileSync, writeFileSync } from "fs";

const SRC = readFileSync("codegen/webgpu.h").toString("utf8");

const IS_PY12 = false;
const EMIT_CDEF = true;

interface FuncArg {
  name: string;
  explicitPointer: boolean;
  explicitConst: boolean;
  ctype: CType;
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
  emit?(api: ApiInfo): string;
  addFunc?(func: CFunc): void;
}

interface CEnumVal {
  name: string;
  val: string;
}

function quoted(s: string): string {
  if (s.startsWith('"')) {
    return s;
  }
  return `"${s}"`;
}

function sanitizeIdent(ident: string): string {
  if (!ident.match(/^[a-zA-Z]/) || ident === "None") {
    ident = "_" + ident;
  }
  return ident;
}

type ParseState = { lines: string[]; pos: number };

function discardProcs(state: ParseState) {
  const { lines } = state;
  if (!lines[state.pos].includes("WGPU_SKIP_PROCS")) {
    throw new Error(`Discard procs called at wrong position: ${state.pos}`);
  }
  ++state.pos;
  while (state.pos < lines.length) {
    if (lines[state.pos].includes("WGPU_SKIP_PROCS")) {
      console.log("SKIPPED TO:", state.pos);
      return;
    }
    ++state.pos;
  }
}

const ATTRIBUTES: string[] = [
  "WGPU_OBJECT_ATTRIBUTE",
  "WGPU_ENUM_ATTRIBUTE",
  "WGPU_STRUCTURE_ATTRIBUTE",
  "WGPU_FUNCTION_ATTRIBUTE",
  "WGPU_NULLABLE",
  "WGPU_EXPORT",
];
function cleanLine(line: string): string {
  for (const attrib of ATTRIBUTES) {
    line = line.replaceAll(attrib, "");
  }
  return line;
}

function cleanHeader(src: string): string {
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
    frags.push(cleanLine(rawline));
    ++state.pos;
  }
  return frags.join("\n");
}

class CEnum implements CType {
  kind: "enum" = "enum";
  sanitized: { name: string; val: string }[];

  constructor(
    public cName: string,
    public pyName: string,
    public values: CEnumVal[]
  ) {
    this.sanitized = [];
    for (const { name, val } of this.values) {
      if (name !== "Force32") {
        this.sanitized.push({ name: sanitizeIdent(name), val });
      }
    }
  }

  pyAnnotation(): string {
    return quoted(this.pyName);
  }

  wrap(val: string): string {
    return `${this.pyName}(${val})`;
  }

  unwrap(val: string): string {
    return `int(${val})`;
  }

  emit(): string {
    let frags: string[] = [`class ${this.pyName}(IntEnum):`];
    for (const { name, val } of this.sanitized) {
      frags.push(`    ${name} = ${val}`);
    }
    return frags.join("\n") + "\n";
  }
}

class CFlags implements CType {
  kind: "enum" = "enum";

  constructor(
    public cName: string,
    public pyName: string,
    public etype: CEnum
  ) {}

  pyAnnotation(): string {
    return quoted(this.pyName);
  }

  wrap(val: string): string {
    return `${this.pyName}(${val})`;
  }

  unwrap(val: string): string {
    return `int(${val})`;
  }

  emit(): string {
    const etypename = this.etype.pyAnnotation();

    const props: string[] = [];
    for (const { name, val } of this.etype.sanitized) {
      if (parseInt(val) === 0) {
        continue;
      }
      props.push(`
    @property
    def ${name}(self) -> bool:
        return (self.value & ${val}) > 0

    @${name}.setter
    def ${name}(self, enabled: bool):
        if enabled:
            self.value |= ${val}
        else:
            self.value &= ~(${val})`);
    }

    return (
      `
class ${this.etype.pyName}Flags:
    def __init__(self, flags: ${pyUnion(`list[${etypename}]`, `int`)}):
        if isinstance(flags, int):
            self.value = flags
        else:
            self.value = sum(set(flags))

    def __int__(self) -> int:
        return self.value
    ` + props.join("\n")
    );
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

interface Emittable {
  emit(): string;
}

class ApiInfo {
  types: Map<string, CType> = new Map();
  wrappers: Map<string, Emittable> = new Map();
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
      pyAnnotation: (isPointer) => (isPointer ? "VoidPtr" : "None"),
      wrap: (v, isPointer) => {
        if (isPointer) {
          // HORRIBLE HACK: assumes "size" is an argument!
          return `VoidPtr(${v}, size)`;
        }
        return v;
      },
      unwrap: (v, isPointer) => {
        if (isPointer) {
          return `${v}._ptr`;
        }
        return v;
      },
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

  createWrapperOnce(name: string, create: () => Emittable) {
    if (!this.wrappers.has(name)) {
      this.wrappers.set(name, create());
    }
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

  getListWrapper(ctype: CType): string {
    this.createWrapperOnce(
      `_LIST_${ctype.cName}`,
      () => new ListWrapper(ctype)
    );
    return listName(ctype.pyName);
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
        const innerCType = this.getType(arrType);
        this.getListWrapper(innerCType);
        fields.push(new ArrayField(arrName, name, innerCType));
        fieldPos += 2;
      } else if (
        name.endsWith("Callback") &&
        fieldPos + 1 < rawFields.length &&
        rawFields[fieldPos + 1].name.endsWith("Userdata")
      ) {
        fields.push(new CallbackField(name, this.getType(type)));
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
    const fpointer = new CFuncPointer(name, toPyName(name, true), args, ret);

    this.types.set(name, fpointer);
    this.wrappers.set(`_cbwrap_${name}`, new CallbackWrapper(fpointer));
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

  findBitflags(src: string) {
    const reg = /typedef WGPUFlags ([A-Za-z0-9]*)Flags WGPU_ENUM_ATTRIBUTE;/g;
    for (const m of src.matchAll(reg)) {
      const [_wholeMatch, enumType] = m;
      const ee = this.types.get(enumType);
      if (ee === undefined || !(ee instanceof CEnum)) {
        console.log(`Couldn't find enum corresponding to "${enumType}"!`);
        continue;
      }
      const cname = `${enumType}Flags`;
      const pyName = toPyName(cname, true);

      this.types.set(cname, new CFlags(cname, pyName, ee));
    }
  }

  prepFuncCall(func: CFunc): [string[], string[]] {
    let pyArglist = ["self"];
    let callArglist = ["self._cdata"];
    const args = func.args;
    let idx = 1;
    while (idx < args.length) {
      const arg = args[idx];
      const next = args[idx + 1];
      if (
        next !== undefined &&
        arg.ctype.cName === "size_t" &&
        arg.name.endsWith("Count")
      ) {
        // assume this is a (count, ptr) combo
        const lname = this.getListWrapper(next.ctype);
        pyArglist.push(`${next.name}: ${quoted(lname)}`);
        callArglist.push(`${next.name}._count`);
        callArglist.push(`${next.name}._ptr`);
        idx += 2;
      } else if (
        arg.ctype.cName === "void" &&
        arg.explicitPointer &&
        next?.ctype.cName === "size_t" &&
        next?.name.toLowerCase().endsWith("size")
      ) {
        // assume a (void ptr, size) pair
        pyArglist.push(
          `${arg.name}: ${arg.ctype.pyAnnotation(arg.explicitPointer)}`
        );
        callArglist.push(`${arg.name}._ptr`);
        callArglist.push(`${arg.name}._size`);
        idx += 2;
      } else if (arg.name === "callback") {
        // assume a (callback, userdata) combo
        pyArglist.push(
          `${arg.name}: ${arg.ctype.pyAnnotation(arg.explicitPointer)}`
        );
        callArglist.push(`${arg.name}._ptr`);
        callArglist.push(`${arg.name}._userdata`);
        idx += 2;
      } else {
        pyArglist.push(
          `${arg.name}: ${arg.ctype.pyAnnotation(arg.explicitPointer)}`
        );
        callArglist.push(arg.ctype.unwrap(arg.name, arg.explicitPointer));
        ++idx;
      }
    }
    return [pyArglist, callArglist];
  }

  parse(src: string) {
    this.findEnums(src);
    this.findBitflags(src);
    this.findOpaquePointers(src);
    this.findCallbackTypes(src);
    this.findConcreteStructs(src);
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
    return quoted(this.pyName);
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
}

interface CStructField {
  name: string;
  ctype: CType;
  prop(): string;
  arg(): string;
}

function listName(pyname: string): string {
  return `${pyname}List`;
}

class ArrayField implements CStructField {
  constructor(
    public name: string,
    public countName: string,
    public ctype: CType
  ) {}

  arg(): string {
    return `${this.name}: ${quoted(listName(this.ctype.pyName))}`;
  }

  prop(): string {
    return `
@property
def ${this.name}(self) -> ${quoted(listName(this.ctype.pyName))}:
    return self._${this.name}

@${this.name}.setter
def ${this.name}(self, v: ${quoted(listName(this.ctype.pyName))}):
    self._${this.name} = v
    self._cdata.${this.countName} = v._count
    self._cdata.${this.name} = v._ptr`;
  }
}

// hate that I have to special case for like one struct that
// has embedded callbacks!
class CallbackField implements CStructField {
  constructor(public name: string, public ctype: CType) {}

  arg(): string {
    return `${this.name}: ${this.ctype.pyAnnotation(false)}`;
  }

  prop(): string {
    return `
@property
def ${this.name}(self) -> ${this.ctype.pyAnnotation(false)}:
    return self._${this.name}

@${this.name}.setter
def ${this.name}(self, v: ${this.ctype.pyAnnotation(false)}):
    self._${this.name} = v
    self._cdata.${this.name} = v._ptr
    self._cdata.${this.name.replaceAll("Callback", "Userdata")} = v._userdata
    `;
  }
}

class ValueField implements CStructField {
  constructor(public name: string, public ctype: CType) {}

  arg(): string {
    return `${this.name}: ${this.ctype.pyAnnotation(false)}`;
  }

  prop(): string {
    return `
@property
def ${this.name}(self) -> ${this.ctype.pyAnnotation(false)}:
    return ${this.ctype.wrap(`self._cdata.${this.name}`, false)}

@${this.name}.setter
def ${this.name}(self, v: ${this.ctype.pyAnnotation(false)}):
    self._cdata.${this.name} = ${this.ctype.unwrap("v", false)}`;
  }
}

function pyOptional(pyType: string): string {
  return IS_PY12 ? `${pyType} | None` : `Optional[${pyType}]`;
}

function pyUnion(a: string, b: string): string {
  return IS_PY12 ? `${a} | ${b}` : `Union[${a}, ${b}]`;
}

class PointerField implements CStructField {
  constructor(
    public name: string,
    public ctype: CType,
    public nullable: boolean
  ) {}

  argtype(): string {
    const annotation = this.ctype.pyAnnotation(true);
    return this.nullable ? pyOptional(annotation) : annotation;
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
  return `_ffi_new("${ptrTo(ctype)}")`;
}

class COpaque implements CType {
  kind: "opaque" = "opaque";
  funcs: Map<string, CFunc> = new Map();

  constructor(public cName: string, public pyName: string) {}

  pyAnnotation(): string {
    return quoted(this.pyName);
  }

  wrap(val: string): string {
    return `${this.pyName}(${val})`;
  }

  unwrap(val: string): string {
    return `${val}._cdata`;
  }

  addFunc(func: CFunc): void {
    const pyFname = toPyName(
      removePrefixCaseInsensitive(func.name, this.cName)
    );
    console.log(`Adding ${func.name} (${pyFname}) to ${this.cName}`);
    this.funcs.set(pyFname, func);
  }

  emitFunc(api: ApiInfo, pyFname: string, func: CFunc): string {
    const [pyArglist, callArglist] = api.prepFuncCall(func);

    let retval = "";
    let theCall = `lib.${func.name}(${callArglist.join(", ")})`;
    if (func.ret !== undefined) {
      theCall = func.ret.ctype.wrap(theCall, func.ret.explicitPointer);
      retval = ` -> ${func.ret.ctype.pyAnnotation(func.ret.explicitPointer)}`;
    }

    return `
    def ${pyFname}(${pyArglist.join(", ")})${retval}:
        return ${theCall}`;
  }

  emit(api: ApiInfo): string {
    const funcdefs: string[] = [];
    for (const [pyFname, func] of this.funcs.entries()) {
      funcdefs.push(this.emitFunc(api, pyFname, func));
    }
    const reffer = this.funcs.get("reference");
    const releaser = this.funcs.get("release");
    if (reffer === undefined || releaser === undefined) {
      throw new Error(`Opaque ${this.cName} missing reference or release!`);
    }

    return `
class ${this.pyName}:
    def __init__(self, cdata: CData):
        self._cdata = ffi.gc(cdata, lib.${releaser.name})
${funcdefs.join("\n")}
`;
  }
}

class CallbackWrapper implements Emittable {
  constructor(public func: CFuncPointer) {}

  emit(): string {
    const args = this.func.args;
    const rawArglist = args.map((arg) => arg.name);
    const arglist = args
      .slice(0, args.length - 1)
      .map((arg) => arg.ctype.pyAnnotation(arg.explicitPointer));
    const unpackList = args
      .slice(0, args.length - 1)
      .map((arg) => arg.ctype.wrap(arg.name, arg.explicitPointer));
    const pytype = `Callable[[${arglist}], ${this.func.ret.ctype.pyAnnotation(
      this.func.ret.explicitPointer
    )}]`;

    const mapName = `_callback_map_${this.func.pyName}`;
    const rawName = `_raw_callback_${this.func.pyName}`;
    return `
${mapName} = CBMap()

def ${rawName}(${rawArglist.join(", ")}):
    idx = _cast_userdata(userdata)
    cb = ${mapName}.get(idx)
    if cb is not None:
        cb(${unpackList.join(", ")})

class ${this.func.pyName}:
    def __init__(self, callback: ${pytype}):
        self.index = ${mapName}.add(callback)
        self._userdata = _ffi_new("int[]", 1)
        self._userdata[0] = self.index
        self._ptr = ${rawName}

    def remove(self):
        ${mapName}.remove(self.index)
    `;
  }
}

class ListWrapper implements Emittable {
  constructor(public ctype: CType) {}

  emit(): string {
    return `
class ${listName(this.ctype.pyName)}:
    def __init__(self, items: list[${this.ctype.pyAnnotation(false)}]):
        self._count = len(items)
        self._ptr = _ffi_new('${this.ctype.cName}[]', self._count)
        for idx, item in enumerate(items):
            self._ptr[idx] = ${this.ctype.unwrap("item", false)}`;
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
    return quoted(this.pyName);
  }

  wrap(val: string): string {
    return `raise ValueError("This property cannot be queried!")`;
  }

  unwrap(val: string): string {
    return `${val}._cdata`;
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
// * chained structs
// * mutated by value structs (wrapping values back?)
// * bind wgpu-native specific functions from wgpu.h? (at least poll is needed!)

// * cleanup: merge all the types into just CType
// * default arguments? maybe better to not have any defaults!

// QUESTIONS:
// * do we need to explicitly call `reference` on returned things?

// NICE TO HAVE:
// * pretty printing
// * maybe use https://cffi.readthedocs.io/en/stable/ref.html#ffi-new-handle-ffi-from-handle
//   instead of current int userdata approach? (could store callback itself as handle?)

const api = new ApiInfo();
api.parse(SRC);

const pyFrags: string[] = [];

pyFrags.push("# Basic types");
for (const [_name, ctype] of api.types.entries()) {
  if (ctype.emit) {
    pyFrags.push(ctype.emit(api));
  }
}

pyFrags.push("# Util wrapper types");
for (const [_name, emitter] of api.wrappers.entries()) {
  pyFrags.push(emitter.emit());
}

const cdef = EMIT_CDEF ? `ffi.cdef("""${cleanHeader(SRC)}""")` : ``;

const finalOutput = `# AUTOGENERATED
from collections.abc import Callable
from enum import IntEnum
from typing import Any, Optional, Union

from cffi import FFI

ffi = FFI()
# TODO: figure out DLL name on different platforms!
lib: Any = ffi.dlopen("wgpu_native.dll")

# make typing temporarily happy until I can figure out if there's
# a better way to have type information about CData fields
CData = Any

${cdef}

def _ffi_new(typespec: str, count: ${pyOptional("int")} = None) -> CData:
    return ffi.new(typespec, count)

def _cast_userdata(ud: CData) -> int:
    return ffi.cast("int *", ud)[0]

class CBMap:
    def __init__(self):
        self.callbacks = {}
        self.index = 0

    def add(self, cb) -> int:
        retidx = self.index
        self.index += 1
        self.callbacks[retidx] = cb
        return retidx

    def get(self, idx):
        return self.callbacks.get(idx)

    def remove(self, idx):
        if idx in self.callbacks:
            del self.callbacks[idx]

class VoidPtr:
    def __init__(self, data: CData, size: ${pyOptional("int")} = None):
        self._ptr = data
        self._size = size

${pyFrags.join("\n")}
`;

writeFileSync("webgoo.py", finalOutput);
