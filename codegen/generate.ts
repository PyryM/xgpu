console.log("Hello via Bun!");

const EXAMPLE = `
typedef enum WGPUCompareFunction {
  WGPUCompareFunction_Undefined = 0x00000000,
  WGPUCompareFunction_Never = 0x00000001,
  WGPUCompareFunction_Less = 0x00000002,
  WGPUCompareFunction_LessEqual = 0x00000003,
  WGPUCompareFunction_Greater = 0x00000004,
  WGPUCompareFunction_GreaterEqual = 0x00000005,
  WGPUCompareFunction_Equal = 0x00000006,
  WGPUCompareFunction_NotEqual = 0x00000007,
  WGPUCompareFunction_Always = 0x00000008,
  WGPUCompareFunction_Force32 = 0x7FFFFFFF
} WGPUCompareFunction WGPU_ENUM_ATTRIBUTE;

typedef enum WGPUCompilationInfoRequestStatus {
  WGPUCompilationInfoRequestStatus_Success = 0x00000000,
  WGPUCompilationInfoRequestStatus_Error = 0x00000001,
  WGPUCompilationInfoRequestStatus_DeviceLost = 0x00000002,
  WGPUCompilationInfoRequestStatus_Unknown = 0x00000003,
  WGPUCompilationInfoRequestStatus_Force32 = 0x7FFFFFFF
} WGPUCompilationInfoRequestStatus WGPU_ENUM_ATTRIBUTE;

typedef enum WGPUCompilationMessageType {
  WGPUCompilationMessageType_Error = 0x00000000,
  WGPUCompilationMessageType_Warning = 0x00000001,
  WGPUCompilationMessageType_Info = 0x00000002,
  WGPUCompilationMessageType_Force32 = 0x7FFFFFFF
} WGPUCompilationMessageType WGPU_ENUM_ATTRIBUTE;
`;

interface CEnumVal {
  name: string;
  val: string;
}

interface CEnum {
  name: string;
  entries: CEnumVal[];
}

function cleanup(s: string, prefix: string): string {
  s = s.trim();
  if (s.startsWith(prefix)) {
    s = s.slice(prefix.length);
  }
  if (s.startsWith("_")) {
    s = s.slice(1);
  }
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

const enums = findEnums(EXAMPLE);
for (const { name, entries } of enums) {
  console.log(name);
  for (const entry of entries) {
    console.log(`[${entry.name}], [${entry.val}]`);
  }
}
