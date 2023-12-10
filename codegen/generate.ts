import { readFileSync, writeFileSync } from "fs";
import {
  cleanup,
  removePrefix,
  removePrefixCaseInsensitive,
  sanitizeIdent,
  quoted,
  cleanHeader,
  recase,
  indent2,
  indent,
} from "./stringmanip";

const HEADERS = ["codegen/webgpu.h", "codegen/wgpu_extra.h"];
const SRC = HEADERS.map((fn) => readFileSync(fn).toString("utf8")).join("\n");

const IS_PY12 = false;

const SPECIAL_CLASSES: Set<string> = new Set([
  "WGPUChainedStruct",
  "WGPUChainedStructOut",
]);

const BAD_FUNCTIONS: Map<string, string> = new Map([
  ["wgpuAdapterEnumerateFeatures", "This is unsafe. Use hasFeature."],
  ["wgpuDeviceEnumerateFeatures", "This is unsafe. Use hasFeature."],
  ["wgpuGetProcAddress", "Untyped function pointer return."],
]);

interface FuncArg {
  name: string;
  explicitPointer: boolean;
  explicitConst: boolean;
  nullable: boolean;
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
  wrap(val: string, isPointer: boolean, parent?: string): string;
  unwrap(val: string, isPointer: boolean): string;
  preStore?(target: string, val: string): [string, string];
  emit?(api: ApiInfo): string;
  addFunc?(func: CFunc): void;
}

interface CEnumVal {
  name: string;
  val: string;
}

function pyOptional(pyType: string): string {
  return IS_PY12 ? `${pyType} | None` : `Optional[${pyType}]`;
}

function pyUnion(a: string, b: string): string {
  return IS_PY12 ? `${a} | ${b}` : `Union[${a}, ${b}]`;
}

function onlyDefined<T>(items: (T | undefined)[]): T[] {
  const res: T[] = [];
  for (const item of items) {
    if (item !== undefined) {
      res.push(item);
    }
  }
  return res;
}

export const EMPTY_DEFINES: string[] = [
  "WGPU_OBJECT_ATTRIBUTE",
  "WGPU_ENUM_ATTRIBUTE",
  "WGPU_STRUCTURE_ATTRIBUTE",
  "WGPU_FUNCTION_ATTRIBUTE",
  "WGPU_NULLABLE",
  "WGPU_EXPORT",
];

class CEnum implements CType {
  kind: "enum" = "enum";
  sanitized: { name: string; val: string }[] = [];
  values: CEnumVal[] = [];

  constructor(public cName: string, public pyName: string, values: CEnumVal[]) {
    this.mergeValues(values);
  }

  mergeValues(values: CEnumVal[]) {
    for (const { name, val } of values) {
      this.values.push({ name, val });
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
class ${this.pyName}:
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

function parseEnumEntry(
  parentName: string,
  entry: string
): CEnumVal | undefined {
  if (!entry.includes("=")) {
    return undefined;
  }
  const [name, val] = entry.split("=").map((e) => e.trim());
  return { name: cleanup(name, parentName), val };
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
    } else if (part === "struct") {
      // don't do anything
    } else {
      info.inner = part;
    }
  }
  if (info.explicitPointer && info.inner.startsWith("WGPUChainedStruct")) {
    // chained struct pointers are always nullable?
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
  emit(api: ApiInfo): string;
  emitCDef?(api: ApiInfo): string;
}

class ApiInfo {
  types: Map<string, CType> = new Map();
  wrappers: Map<string, Emittable> = new Map();
  UNKNOWN_TYPE: CType = prim("UNKNOWN", "UNKNOWN");
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
      ["WGPUSubmissionIndex", "int"],
      ["UNKNOWN", "UNKNOWN"],
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
      wrap: (v, isPointer) => (isPointer ? `_ffi_string(${v})` : v),
      unwrap: (v) => `_ffi_unwrap_str(${v})`,
      preStore: (target, val) => [
        `${target} = _ffi_unwrap_str(${val})`,
        target,
      ],
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
    const ret = this.types.get(t);
    if (ret === undefined) {
      console.log("MISSING:", t);
      return this.UNKNOWN_TYPE;
    }
    return ret;
  }

  findEnums(src: string) {
    const enumExp = /typedef enum ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
    for (const [_wholeMatch, name, body] of src.matchAll(enumExp)) {
      const entries = onlyDefined(
        body.split(",").map((e) => parseEnumEntry(name.trim(), e))
      );
      const cName = name.trim();
      if (cName === "WGPUNativeSType") {
        // HACK: merge into existing SType enum
        const stypeEnum = this.types.get("WGPUSType") as CEnum;
        const fixedEntries = entries.map(({ name, val }) => ({
          name: removePrefix(name, "WGPUSType_"),
          val,
        }));
        stypeEnum.mergeValues(fixedEntries);
      } else {
        this.types.set(cName, new CEnum(cName, toPyName(cName, true), entries));
      }
    }
  }

  findOpaquePointers(src: string) {
    const reg = /typedef struct ([a-zA-Z0-9]+)\* ([a-zA-Z]+)([^;]*);/g;
    for (const [, , cName] of src.matchAll(reg)) {
      this.types.set(cName, new COpaque(cName, toPyName(cName, true)));
    }
  }

  _createField(name: string, ref: Refinfo): CStructField {
    const type = this.getType(ref);
    if (ref.explicitPointer || type.kind === "opaque") {
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
    const noEmit = SPECIAL_CLASSES.has(cName);
    this.types.set(
      cName,
      new CStruct(cName, toPyName(cName, true), cdef, fields, noEmit)
    );
  }

  findConcreteStructs(src: string) {
    const reg = /typedef struct ([a-zA-Z0-9]*) \{([^\}]*)\}/g;
    for (const [cdef, name, rawBody] of src.matchAll(reg)) {
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
        nullable: false,
      };
    } else {
      const info = parseTypeRef(returnType);
      return {
        name: "return",
        ctype: this.getType(info),
        explicitConst: info.constant === true,
        explicitPointer: info.explicitPointer === true,
        nullable: false,
      };
    }
  }

  _parseFuncArgs(argStr: string): FuncArg[] {
    argStr = argStr.trim();
    if (argStr === "" || argStr === "void") {
      // zero argument function
      return [];
    }

    return argStr.split(",").map((ident) => {
      let { name, type } = parseTypedIdent(ident);
      return {
        name,
        ctype: this.getType(type),
        explicitPointer: type.explicitPointer === true,
        explicitConst: type.constant === true,
        nullable: type.nullable === true,
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
    const ret = this._parseFuncReturn(returnType);
    const fpointer = new CFuncPointer(name, toPyName(name, true), argStr, ret);

    this.types.set(name, fpointer);
    this.wrappers.set(`_cbwrap_${name}`, new CallbackWrapper(fpointer));
  }

  findCallbackTypes(src: string) {
    // typedef void (*WGPUBufferMapCallback)(WGPUBufferMapAsyncStatus status, void * userdata) WGPU_FUNCTION_ATTRIBUTE;
    const reg =
      /typedef (.*) \(\*([A-Za-z0-9]+)\)\((.*)\) WGPU_FUNCTION_ATTRIBUTE;/g;
    for (const [, returnType, name, args] of src.matchAll(reg)) {
      if (!name.endsWith("Callback")) {
        continue;
      }
      this._addCallbackType(name, args, returnType);
    }
  }

  findExportedFunctions(src: string) {
    const reg =
      /WGPU_EXPORT (.*) ([a-zA-Z0-9_]+)\((.*)\) WGPU_FUNCTION_ATTRIBUTE;/g;
    for (const [, returnType, name, args] of src.matchAll(reg)) {
      this._addFunc(name, args, returnType);
    }
  }

  findBitflags(src: string) {
    const reg = /typedef WGPUFlags ([A-Za-z0-9]*)Flags WGPU_ENUM_ATTRIBUTE;/g;
    for (const [_wholeMatch, enumType] of src.matchAll(reg)) {
      let ee = this.types.get(enumType);
      if (ee === undefined || !(ee instanceof CEnum)) {
        // hack to deal with special case of
        // "WGPUInstanceFlag" -> "WGPUInstanceFlags"
        ee = this.types.get(enumType + "Flag");
        if (ee === undefined || !(ee instanceof CEnum)) {
          console.log(`Couldn't find enum "${enumType}" or "${enumType}Flag"!`);
          console.log("Whole match:", _wholeMatch);
          continue;
        }
      }
      const cname = `${enumType}Flags`;
      const pyName = toPyName(cname, true);

      this.types.set(cname, new CFlags(cname, pyName, ee));
    }
  }

  prepFuncCall(
    func: CFunc,
    isMemberFunc: boolean
  ): { pyArgs: string[]; callArgs: string[]; staging: string[] } {
    const pyArgs = isMemberFunc ? ["self"] : [];
    const callArgs = isMemberFunc ? ["self._cdata"] : [];
    const staging: string[] = [];

    const args = func.args;
    let idx = isMemberFunc ? 1 : 0;
    while (idx < args.length) {
      const arg = args[idx];
      const next = args[idx + 1];
      if (
        next !== undefined &&
        arg.ctype.cName === "size_t" &&
        arg.name.endsWith("Count")
      ) {
        // assume this is a (count, ptr) combo
        const wrapperName = this.getListWrapper(next.ctype);
        const lname = quoted(wrapperName);
        const maybeList = pyUnion(lname, `list[${next.ctype.pyName}]`);
        pyArgs.push(`${next.name}: ${maybeList}`);
        staging.push(`if isinstance(${next.name}, list):`);
        staging.push(`    ${next.name}_staged = ${wrapperName}(${next.name})`);
        staging.push(`else:`);
        staging.push(`    ${next.name}_staged = ${next.name}`);
        callArgs.push(`${next.name}_staged._count`);
        callArgs.push(`${next.name}_staged._ptr`);
        idx += 2;
      } else if (
        arg.ctype.cName === "void" &&
        arg.explicitPointer &&
        next?.ctype.cName === "size_t" &&
        next?.name.toLowerCase().endsWith("size")
      ) {
        // assume a (void ptr, size) pair
        pyArgs.push(
          `${arg.name}: ${arg.ctype.pyAnnotation(arg.explicitPointer)}`
        );
        callArgs.push(`${arg.name}._ptr`);
        callArgs.push(`${arg.name}._size`);
        idx += 2;
      } else if (arg.name === "callback") {
        // assume a (callback, userdata) combo
        pyArgs.push(
          `${arg.name}: ${arg.ctype.pyAnnotation(arg.explicitPointer)}`
        );
        callArgs.push(`${arg.name}._ptr`);
        callArgs.push(`${arg.name}._userdata`);
        idx += 2;
      } else if (
        arg.nullable &&
        (arg.explicitPointer || arg.ctype.kind === "opaque")
      ) {
        pyArgs.push(
          `${arg.name}: ${pyOptional(
            arg.ctype.pyAnnotation(arg.explicitPointer)
          )}`
        );
        callArgs.push(`_ffi_unwrap_optional(${arg.name})`);
        //callArgs.push(arg.ctype.unwrap(arg.name, arg.explicitPointer));
        ++idx;
      } else {
        pyArgs.push(
          `${arg.name}: ${arg.ctype.pyAnnotation(arg.explicitPointer)}`
        );
        callArgs.push(arg.ctype.unwrap(arg.name, arg.explicitPointer));
        ++idx;
      }
    }
    return { pyArgs, callArgs, staging };
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
    public argStr: string,
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
}

interface CStructField {
  name: string;
  ctype: CType;
  prop(): string;
  arg(noInit?: boolean): string;
}

function listName(pyname: string): string {
  return toPyName(`${pyname}List`, true);
}

class ArrayField implements CStructField {
  constructor(
    public name: string,
    public countName: string,
    public ctype: CType
  ) {}

  listType(): string {
    return quoted(listName(this.ctype.pyName));
  }

  argType(): string {
    return pyUnion(this.listType(), `list[${quoted(this.ctype.pyName)}]`);
  }

  arg(): string {
    return `${this.name}: ${this.argType()}`;
  }

  prop(): string {
    return `
@property
def ${this.name}(self) -> ${this.listType()}:
    return self._${this.name}

@${this.name}.setter
def ${this.name}(self, v: ${this.argType()}):
    if isinstance(v, list):
        v2 = ${listName(this.ctype.pyName)}(v)
    else:
        v2 = v
    self._${this.name} = v2
    self._cdata.${this.countName} = v2._count
    self._cdata.${this.name} = v2._ptr`;
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
    return ${this.ctype.wrap(`self._cdata.${this.name}`, false, "self")}

@${this.name}.setter
def ${this.name}(self, v: ${this.ctype.pyAnnotation(false)}):
    self._cdata.${this.name} = ${this.ctype.unwrap("v", false)}`;
  }
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

  arginit(): string {
    return this.nullable ? " = None" : "";
  }

  arg(noInit: boolean = false): string {
    return `${this.name}: ${this.argtype()}${noInit ? "" : this.arginit()}`;
  }

  setterBody(): string[] {
    let lines: string[] = [`self._${this.name} = v`];
    let unwrapped = this.ctype.unwrap("v", true);
    const storeBody: string[] = [];
    if (this.ctype.preStore) {
      const storeName = `self._store_${this.name}`;
      const [storeCmd, unwrappedStore] = this.ctype.preStore(storeName, "v");
      storeBody.push(storeCmd);
      unwrapped = unwrappedStore;
    }
    storeBody.push(`self._cdata.${this.name} = ${unwrapped}`);

    if (this.nullable) {
      lines.push(`if v is None:`);
      lines.push(`    self._cdata.${this.name} = ffi.NULL`);
      lines.push(`else:`);
      lines = lines.concat(indent2(1, storeBody));
    } else {
      lines = lines.concat(storeBody);
    }
    return lines;
  }

  prop(): string {
    let getter: string = `self._${this.name}`;
    if (this.name !== "nextInChain" && this.ctype.kind === "struct") {
      // special case where we want to return a wrapped pointer
      // to an interior pointer
      getter = `${this.ctype.pyName}(cdata = self._cdata.${this.name}, parent = self)`;
    } else if (this.ctype.pyName === "str") {
      // special case returning strings?
      getter = `_ffi_string(self._cdata.${this.name})`;
    }

    return `
@property
def ${this.name}(self) -> ${this.argtype()}:
    return ${getter}

@${this.name}.setter
def ${this.name}(self, v: ${this.argtype()}):
${indent(1, this.setterBody())}`;
  }
}

function ptrTo(ctype: string): string {
  return `${ctype} *`;
}

function ffiInit(ctype: string, cdata: string): string {
  return `_ffi_init("${ptrTo(ctype)}", ${cdata})`;
}

function getDescriptorArg(
  func: CFunc,
  isMemberFunc: boolean
): CStruct | undefined {
  const expectedArgCount = isMemberFunc ? 2 : 1;
  if (func.args.length !== expectedArgCount) {
    return undefined;
  }
  const maybeDescArg = func.args[expectedArgCount - 1];
  if (
    maybeDescArg.name === "descriptor" &&
    maybeDescArg.ctype.cName.endsWith("Descriptor")
  ) {
    return maybeDescArg.ctype as CStruct;
  }
  return undefined;
}

function emitFuncDef(
  api: ApiInfo,
  pyFname: string,
  func: CFunc,
  isMemberFunc: boolean
): string[] {
  const badReason = BAD_FUNCTIONS.get(func.name);
  if (badReason) {
    return [
      `# ${func.name} is marked as a MISBEHAVED FUNCTION:`,
      `# ${badReason}`,
      ``,
    ];
  }

  const { pyArgs, callArgs, staging } = api.prepFuncCall(func, isMemberFunc);

  let retval = "";
  let theCall = `lib.${func.name}(${callArgs.join(", ")})`;
  if (func.ret !== undefined) {
    theCall = func.ret.ctype.wrap(theCall, func.ret.explicitPointer);
    retval = ` -> ${func.ret.ctype.pyAnnotation(func.ret.explicitPointer)}`;
  }

  const callBody = [...staging, `return ${theCall}`];

  const descriptorType = getDescriptorArg(func, isMemberFunc);

  if (descriptorType) {
    const descArglist = isMemberFunc ? ["self", "*"] : ["*"];
    const descCallList: string[] = [];
    for (const field of descriptorType.publicFields()) {
      descArglist.push(field.arg(false));
      descCallList.push(`${field.name} = ${field.name}`);
    }

    const descInit = toPyName(descriptorType.pyName, false);

    const maybeSelf = isMemberFunc ? "self." : "";
    return [
      `def ${pyFname}FromDesc(${pyArgs.join(", ")})${retval}:`,
      ...indent2(1, callBody),
      ``,
      `def ${pyFname}(${descArglist.join(", ")})${retval}:`,
      `    return ${maybeSelf}${pyFname}FromDesc(${descInit}(${descCallList.join(
        ", "
      )}))`,
      ``,
    ];
  } else {
    return [
      `def ${pyFname}(${pyArgs.join(", ")})${retval}:`,
      ...indent2(1, callBody),
      ``,
    ];
  }
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
    this.funcs.set(pyFname, func);
  }

  emitFunc(api: ApiInfo, pyFname: string, func: CFunc): string {
    return indent(1, emitFuncDef(api, pyFname, func, true));
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

function cTypeAnnotation(arg: FuncArg): string {
  const parts: string[] = [];
  if (arg.explicitConst) {
    parts.push("const");
  }
  parts.push(arg.ctype.cName);
  if (arg.explicitPointer) {
    parts.push("*");
  }
  return parts.join(" ");
}

class CallbackWrapper implements Emittable {
  constructor(public func: CFuncPointer) {}

  resolveArgs(api: ApiInfo): [FuncArg[], FuncArg] {
    return [api._parseFuncArgs(this.func.argStr), this.func.ret];
  }

  rawName(): string {
    return `_raw_callback_${this.func.pyName}`;
  }

  emitCDef(api: ApiInfo): string {
    const [args, ret] = this.resolveArgs(api);
    const arglist = args.map(cTypeAnnotation).join(", ");
    const sig = `${cTypeAnnotation(ret)} ${this.rawName()}(${arglist})`;
    return `extern "Python" ${sig};`;
  }

  emit(api: ApiInfo): string {
    const [args, ret] = this.resolveArgs(api);
    const rawArglist = args.map((arg) => arg.name);
    const arglist = args
      .slice(0, args.length - 1)
      .map((arg) => arg.ctype.pyAnnotation(arg.explicitPointer));
    const unpackList = args
      .slice(0, args.length - 1)
      .map((arg) => arg.ctype.wrap(arg.name, arg.explicitPointer));
    const pytype = `Callable[[${arglist}], ${ret.ctype.pyAnnotation(
      ret.explicitPointer
    )}]`;

    const mapName = `_callback_map_${this.func.pyName}`;
    return `
${mapName} = CBMap()

@ffi.def_extern()
def ${this.rawName()}(${rawArglist.join(", ")}):
    idx = _cast_userdata(userdata)
    cb = ${mapName}.get(idx)
    if cb is not None:
        cb(${unpackList.join(", ")})

class ${this.func.pyName}:
    def __init__(self, callback: ${pytype}):
        self.index = ${mapName}.add(callback)
        self._userdata = _ffi_new("int[]", 1)
        self._userdata[0] = self.index
        self._ptr = lib.${this.rawName()}

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
    public fields: CStructField[],
    public noEmit: boolean = false
  ) {}

  pyAnnotation(): string {
    return quoted(this.pyName);
  }

  wrap(val: string, isPointer: boolean, parent?: string): string {
    return `${this.pyName}(cdata = ${val}, parent = ${parent ?? "None"})`;
  }

  unwrap(val: string, isPointer: boolean): string {
    if (isPointer) {
      return `${val}._cdata`;
    } else {
      return `_ffi_deref(${val}._cdata)`;
    }
  }

  chainable(): boolean {
    // have to special case chainable structs
    // TODO: consider using a ~protocol~ for these instead!
    const { name, ctype } = this.fields[0];
    return name === "chain" && ctype.cName.startsWith("WGPUChainedStruct");
  }

  publicFields(): CStructField[] {
    if (this.chainable()) {
      return this.fields.slice(1, this.fields.length);
    }
    return this.fields;
  }

  initArgList(): string {
    return this.publicFields()
      .map((f) => f.arg())
      .join(", ");
  }

  emit(): string {
    if (this.noEmit) {
      return `# ${this.pyName} is specially defined elsewhere`;
    }

    const chainable = this.chainable();
    const className = this.pyName;
    const conName = toPyName(className, false);
    const classdef = `class ${className}${chainable ? "(Chainable)" : ""}`;

    const init: string[] = [
      `def __init__(self, *, cdata: ${pyOptional(
        "CData"
      )} = None, parent: ${pyOptional("Any")} = None):`,
      `    self._parent = parent`,
      `    self._cdata = ${ffiInit(this.cName, "cdata")}`,
    ];
    const conlines: string[] = [
      `ret = ${className}(cdata = None, parent = None)`,
    ];

    const props: string[] = [];
    for (const f of this.publicFields()) {
      conlines.push(`ret.${f.name} = ${f.name}`);
      props.push(indent(1, f.prop()));
    }
    conlines.push(`return ret`);

    if (chainable) {
      props.push(``);
      props.push(`    @property`);
      props.push(`    def _chain(self) -> Any:`);
      props.push(`        return self._cdata.chain`);

      init.push(`    self._cdata.chain.sType = SType.${className}`);
    }

    return `
${classdef}:
${indent(1, init.join("\n"))}
${props.join("\n")}

def ${conName}(*, ${this.initArgList()}) -> ${className}:
${indent(1, conlines.join("\n"))}
`;
  }
}

// TODO/THOUGHTS:
// * cleanup: list-of-lists indent flattening?

// ERGONOMICS:
// * Flags could auto-cast an int?
// * callbacks could auto-cast?

// KNOWN ISSUES:
// * building extension w/ dll needs to renamed
//   'wgpu_native.dll.lib' -> 'wgpu_native.lib'

// * Adapter.enumerateFeatures: shoves features into an-array-by-pointer
//  (The way you're supposed to use this function is HACKY:
//   first you call it with null and it returns how many features, then
//   you allocate space and call again with pointer to that space!)

// * cleanup: merge all the types into just CType
//   * have .isPointer, and .inner
//   * have a .resolve() that can deal w/ forward references
// * default arguments? maybe better to not have any defaults!

// QUESTIONS:
// * do we need to explicitly call `reference` on returned things?

// * less manual way of dealing with wgpu.h
// * pretty printing
// * maybe use https://cffi.readthedocs.io/en/stable/ref.html#ffi-new-handle-ffi-from-handle
//   instead of current int userdata approach? (could store callback itself as handle?)

const api = new ApiInfo();

const SRC_NO_COMMENTS = SRC.split("\n")
  .filter((line) => !line.trim().startsWith("//"))
  .join("\n");
api.parse(SRC_NO_COMMENTS);

const pyFrags: string[] = [];
const cdefFrags: string[] = [cleanHeader(SRC, EMPTY_DEFINES)];

pyFrags.push("# Basic types");
for (const [_name, ctype] of api.types.entries()) {
  if (ctype.emit) {
    pyFrags.push(ctype.emit(api));
  }
}

pyFrags.push("# Loose functions");
for (const func of api.looseFuncs) {
  pyFrags.push(
    emitFuncDef(api, toPyName(func.name, false), func, false).join("\n")
  );
}

pyFrags.push("# Util wrapper types");
for (const [_name, emitter] of api.wrappers.entries()) {
  pyFrags.push(emitter.emit(api));
  if (emitter.emitCDef) {
    cdefFrags.push(emitter.emitCDef(api));
  }
}

const cdefSrc = cdefFrags.join("\n");

const cffiBuilderOutput = `# AUTOGENERATED
from cffi import FFI

ffibuilder = FFI()

CDEF = """${cdefSrc}"""
SOURCE = """
#include "codegen/wgpu.h"
"""

ffibuilder.cdef(CDEF)
ffibuilder.set_source(
    "_wgpu_native_cffi", 
    SOURCE, 
    libraries=['wgpu_native'],
    library_dirs=['.']
)   

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
`;

const pylibOutput = `# AUTOGENERATED
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import IntEnum
from typing import Any, Optional, Union

from _wgpu_native_cffi import ffi, lib

# NOTE: this is the runtime-abi linked version for reference
# from cffi import FFI
# ffi = FFI()
# TODO: figure out DLL name on different platforms!
# lib: Any = ffi.dlopen("wgpu_native.dll")

# make typing temporarily happy until I can figure out if there's
# a better way to have type information about CData fields
CData = Any

def _ffi_new(typespec: str, count: ${pyOptional("int")} = None) -> CData:
    return ffi.new(typespec, count)

def _ffi_init(typespec: str, initializer: ${pyOptional("Any")}) -> CData:
    if initializer is None:
        return ffi.new(typespec)
    else:
        return initializer

def _ffi_deref(cdata):
    if ffi.typeof(cdata).kind == 'pointer':
        return cdata[0]
    else:
        return cdata

def _ffi_unwrap_optional(val):
    if val is None:
        return ffi.NULL
    else:
        return val._cdata

def _ffi_unwrap_str(val: ${pyOptional("str")}):
    if val is None:
        val = ""
    return ffi.new("char[]", val.encode("utf8"))

def _ffi_string(val) -> str:
    if val == ffi.NULL:
        return ""
    ret = ffi.string(val)
    if isinstance(ret, bytes):
        return ret.decode("utf8")
    elif isinstance(ret, str):
        return ret
    else:
        raise RuntimeError("IMPOSSIBLE")

def _cast_userdata(ud: CData) -> int:
    return ffi.cast("int *", ud)[0]

class Chainable(ABC):
    @property
    @abstractmethod
    def _chain(self) -> Any:
        ...

class ChainedStruct:
    def __init__(self, chain: list["Chainable"]):
        self.chain = chain
        if len(chain) == 0:
            self._cdata = ffi.NULL
            return
        self._cdata = ffi.addressof(chain[0]._chain)
        next_ptrs = [ffi.addressof(link._chain) for link in chain[1:]] + [ffi.NULL]
        for idx, ptr in enumerate(next_ptrs):
            chain[idx]._chain.next = ptr

# TODO: figure out a nicer way to generically handle this
# (because despite being layout-identical these two types
#  are actually different!)
ChainedStructOut = ChainedStruct

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

    def to_bytes(self) -> bytes:
        return bytes(ffi.buffer(self._ptr, self._size))

${pyFrags.join("\n")}
`;

writeFileSync("wgpu_native_build.py", cffiBuilderOutput);
writeFileSync("webgoo.py", pylibOutput);
