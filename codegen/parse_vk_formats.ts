import { readFileSync } from "fs";

function removeComments(src: string): string {
  return src.split("\n").filter((line) => !line.trim().startsWith("//")).join("\n");
}

const WGPU_FORMATS = [
  "Undefined",
  "R8Unorm",
  "R8Snorm",
  "R8Uint",
  "R8Sint",
  "R16Uint",
  "R16Sint",
  "R16Float",
  "RG8Unorm",
  "RG8Snorm",
  "RG8Uint",
  "RG8Sint",
  "R32Float",
  "R32Uint",
  "R32Sint",
  "RG16Uint",
  "RG16Sint",
  "RG16Float",
  "RGBA8Unorm",
  "RGBA8UnormSrgb",
  "RGBA8Snorm",
  "RGBA8Uint",
  "RGBA8Sint",
  "BGRA8Unorm",
  "BGRA8UnormSrgb",
  "RGB10A2Uint",
  "RGB10A2Unorm",
  "RG11B10Ufloat",
  "RGB9E5Ufloat",
  "RG32Float",
  "RG32Uint",
  "RG32Sint",
  "RGBA16Uint",
  "RGBA16Sint",
  "RGBA16Float",
  "RGBA32Float",
  "RGBA32Uint",
  "RGBA32Sint",
  "Stencil8",
  "Depth16Unorm",
  "Depth24Plus",
  "Depth24PlusStencil8",
  "Depth32Float",
  "Depth32FloatStencil8",
  "BC1RGBAUnorm",
  "BC1RGBAUnormSrgb",
  "BC2RGBAUnorm",
  "BC2RGBAUnormSrgb",
  "BC3RGBAUnorm",
  "BC3RGBAUnormSrgb",
  "BC4RUnorm",
  "BC4RSnorm",
  "BC5RGUnorm",
  "BC5RGSnorm",
  "BC6HRGBUfloat",
  "BC6HRGBFloat",
  "BC7RGBAUnorm",
  "BC7RGBAUnormSrgb",
  "ETC2RGB8Unorm",
  "ETC2RGB8UnormSrgb",
  "ETC2RGB8A1Unorm",
  "ETC2RGB8A1UnormSrgb",
  "ETC2RGBA8Unorm",
  "ETC2RGBA8UnormSrgb",
  "EACR11Unorm",
  "EACR11Snorm",
  "EACRG11Unorm",
  "EACRG11Snorm",
  "ASTC4x4Unorm",
  "ASTC4x4UnormSrgb",
  "ASTC5x4Unorm",
  "ASTC5x4UnormSrgb",
  "ASTC5x5Unorm",
  "ASTC5x5UnormSrgb",
  "ASTC6x5Unorm",
  "ASTC6x5UnormSrgb",
  "ASTC6x6Unorm",
  "ASTC6x6UnormSrgb",
  "ASTC8x5Unorm",
  "ASTC8x5UnormSrgb",
  "ASTC8x6Unorm",
  "ASTC8x6UnormSrgb",
  "ASTC8x8Unorm",
  "ASTC8x8UnormSrgb",
  "ASTC10x5Unorm",
  "ASTC10x5UnormSrgb",
  "ASTC10x6Unorm",
  "ASTC10x6UnormSrgb",
  "ASTC10x8Unorm",
  "ASTC10x8UnormSrgb",
  "ASTC10x10Unorm",
  "ASTC10x10UnormSrgb",
  "ASTC12x10Unorm",
  "ASTC12x10UnormSrgb",
  "ASTC12x12Unorm",
  "ASTC12x12UnormSrgb",
];

const WGPU_SEEN: Map<string, boolean> = new Map();
for(const name of WGPU_FORMATS) {
  WGPU_SEEN.set(`xg.TextureFormat.${name}`, false);
}

const PART_REPLACEMENTS: Map<string, string> = new Map([
  ["UNORM", "Unorm"],
  ["SNORM", "Snorm"],
  ["SRGB", "Srgb"],
  ["UINT", "Uint"],
  ["SINT", "Sint"],
  ["FLOAT", "Float"],
  ["SFLOAT", "Float"],
  ["B8G8R8A8", "BGRA8"],
  ["R8G8B8A8", "RGBA8"],
  ["R8G8", "RG8"],
  ["R16G16B16A16", "RGBA16"],
  ["R16G16B16", "RGB16"],
  ["R16G16", "RG16"],
  ["R32G32B32A32", "RGBA32"],
  ["R32G32B32", "RGB32"],
  ["R32G32", "RG32"],
  ["R8G8B8", "RGB8"],
  ["D32", "Depth32"],
  ["D16", "Depth16"],
  ["BLOCK", ""],
  ["UNDEFINED", "Undefined"]
])

const ASTC_SIZES = [
  "4x4",
  "5x4",
  "5x5",
  "6x5",
  "6x6",
  "8x5",
  "8x6",
  "8x8",
  "10x5",
  "10x6",
  "10x8",
  "10x10",
  "12x10",
  "12x12",
]

const FULL_REPLACEMENTS: Map<string, string> = new Map([
  ["VK_FORMAT_B8G8R8A8_SRGB", "xg.TextureFormat.BGRA8UnormSrgb"],
  ["VK_FORMAT_R8G8B8A8_SRGB", "xg.TextureFormat.RGBA8UnormSrgb"],
  ["VK_FORMAT_D24_UNORM_S8_UINT", "xg.TextureFormat.Depth24PlusStencil8"],
  ["VK_FORMAT_D32_SFLOAT_S8_UINT", "xg.TextureFormat.Depth32FloatStencil8"],
  ["VK_FORMAT_X8_D24_UNORM_PACK32", "xg.TextureFormat.Depth24Plus"], // I assume?
  ["VK_FORMAT_S8_UINT", "xg.TextureFormat.Stencil8"],
  ["VK_FORMAT_A2R10G10B10_UINT_PACK32", "xg.TextureFormat.RGB10A2Uint"],
  ["VK_FORMAT_A2B10G10R10_UNORM_PACK32", "xg.TextureFormat.RGB10A2Unorm"],
  ["VK_FORMAT_B10G11R11_UFLOAT_PACK32", "xg.TextureFormat.RG11B10Ufloat"],
  ["VK_FORMAT_E5B9G9R9_UFLOAT_PACK32", "xg.TextureFormat.RGB9E5Ufloat"],
  ["VK_FORMAT_BC1_RGBA_SRGB_BLOCK", "xg.TextureFormat.BC1RGBAUnormSrgb"],
  ["VK_FORMAT_BC2_UNORM_BLOCK", "xg.TextureFormat.BC2RGBAUnorm"],
  ["VK_FORMAT_BC2_SRGB_BLOCK", "xg.TextureFormat.BC2RGBAUnormSrgb"],
  ["VK_FORMAT_BC3_UNORM_BLOCK", "xg.TextureFormat.BC3RGBAUnorm"],
  ["VK_FORMAT_BC3_SRGB_BLOCK", "xg.TextureFormat.BC3RGBAUnormSrgb"],
  ["VK_FORMAT_BC4_UNORM_BLOCK", "xg.TextureFormat.BC4RUnorm"],
  ["VK_FORMAT_BC4_SNORM_BLOCK", "xg.TextureFormat.BC4RSnorm"],
  ["VK_FORMAT_BC5_UNORM_BLOCK", "xg.TextureFormat.BC5RGUnorm"],
  ["VK_FORMAT_BC5_SNORM_BLOCK", "xg.TextureFormat.BC5RGSnorm"],
  ["VK_FORMAT_BC6H_UFLOAT_BLOCK", "xg.TextureFormat.BC6HRGBUfloat"],
  ["VK_FORMAT_BC6H_SFLOAT_BLOCK", "xg.TextureFormat.BC6HRGBFloat"],
  ["VK_FORMAT_BC7_UNORM_BLOCK", "xg.TextureFormat.BC7RGBAUnorm"],
  ["VK_FORMAT_BC7_SRGB_BLOCK", "xg.TextureFormat.BC7RGBAUnormSrgb"],
  ["VK_FORMAT_ETC2_R8G8B8_SRGB_BLOCK", "xg.TextureFormat.ETC2RGB8UnormSrgb"],
  ["VK_FORMAT_ETC2_R8G8B8A1_UNORM_BLOCK", "xg.TextureFormat.ETC2RGB8A1Unorm"],
  ["VK_FORMAT_ETC2_R8G8B8A1_SRGB_BLOCK", "xg.TextureFormat.ETC2RGB8A1UnormSrgb"],
  ["VK_FORMAT_ETC2_R8G8B8A8_UNORM_BLOCK", "xg.TextureFormat.ETC2RGBA8Unorm"],
  ["VK_FORMAT_ETC2_R8G8B8A8_SRGB_BLOCK", "xg.TextureFormat.ETC2RGBA8UnormSrgb"],
  ["VK_FORMAT_EAC_R11G11_UNORM_BLOCK", "xg.TextureFormat.EACRG11Unorm"],
  ["VK_FORMAT_EAC_R11G11_SNORM_BLOCK", "xg.TextureFormat.EACRG11Snorm"],
])

for(const v of ASTC_SIZES) {
  FULL_REPLACEMENTS.set(`VK_FORMAT_ASTC_${v}_SRGB_BLOCK`, `xg.TextureFormat.ASTC${v}UnormSrgb`);
}

function fixPart(part: string): string {
  return PART_REPLACEMENTS.get(part) ?? part;
}

function fixName(name: string): string {
  name = name.trim().replaceAll("VK_FORMAT_", "");
  name = name.split("_").map(fixPart).join("");
  name = FULL_REPLACEMENTS.get(name) ?? name;
  return "xg.TextureFormat." + name;
}

const src = removeComments(readFileSync("codegen/vkformats.txt").toString("utf8"));


console.log("from typing import Dict")
console.log("")
console.log("from .. import bindings as xg")
console.log("")
console.log("VK_FORMAT_TO_XG: Dict[int, xg.TextureFormat] = {")
for(const line of src.split(",")) {
  const [name, val] = line.trim().split("=");
  if(name === undefined || val === undefined) {
    continue;
  }
  const fixedname = FULL_REPLACEMENTS.get(name.trim()) ?? fixName(name);
  if(isFinite(parseInt(val))) {
    const def = `${val}: ${fixedname}, # ${name.trim()}`;
    if(WGPU_SEEN.has(fixedname)) {
      WGPU_SEEN.set(fixedname, true);
      console.log(def);
    } else {
      console.log(`# ${val}: ${name.trim()} (${fixedname})`)
    }
  }
}
console.log("}")

for(const [name, seen] of WGPU_SEEN.entries()) {
  if(!seen) {
    console.log(`# MISSING: ${name}`);
  }
}