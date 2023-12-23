import { platform, arch, release } from "node:os";

async function downloadFile(url: string, localPath: string) {
  const resp = await fetch(url); //, {redirect: "follow"});
  if (resp.status === 404) {
    throw new Error(`404: ${url}`);
  }
  const data = await resp.blob();
  const written = await Bun.write(localPath, data);
  console.log(`Downloaded ${written} bytes -> ${localPath}`);
}

type SrcDest = [string, string];

const ALIASES: Map<string, string> = new Map([
  ["win32", "windows"],
  ["darwin", "macos"],
  ["x64", "x86_64"],
  ["arm", "aarch64"],
  ["arm64", "aarch64"],
]);
const fixname = (s: string) => ALIASES.get(s) ?? s;

const SYSLIBS: Map<string, (string | SrcDest)[]> = new Map([
  ["windows", ["wgpu_native.dll", ["wgpu_native.dll.lib", "wgpu_native.lib"]]],
  ["linux", ["libwgpu_native.so"]],
  ["macos", ["libwgpu_native.dylib"]],
]);

// releases are formatted like:
// https://github.com/gfx-rs/wgpu-native/releases/download/v0.18.1.4/wgpu-linux-x86_64-release.zip
const BASE_URL = "https://github.com/gfx-rs/wgpu-native/releases/download/";
const VERSION = "0.18.1.4";
const IS_WINDOWS = release().toLowerCase().includes("microsoft");
const OS = IS_WINDOWS ? "windows" : fixname(platform());
const ARCH = fixname(arch());
const URL = `${BASE_URL}v${VERSION}/wgpu-${OS}-${ARCH}-release.zip`;

const UNZIP_PATH = "wgpu_native_unzipped";

console.log(`Downloading release from: "${URL}"`);
await downloadFile(URL, "wgpu_native.zip");
await Bun.spawn(["unzip", "-o", "-d", UNZIP_PATH, "wgpu_native.zip"]).exited;

const LIBS: SrcDest[] = (SYSLIBS.get(OS) ?? ["libwgpu_native.so"]).map(
  (lib) => {
    const [src, dest] = typeof lib === "string" ? [lib, lib] : lib;
    return [`${UNZIP_PATH}/${src}`, `webgoo/${dest}`];
  }
);

const COPIES = [
  [`${UNZIP_PATH}/webgpu.h`, "webgoo/include/webgpu.h"],
  [`${UNZIP_PATH}/wgpu.h`, "webgoo/include/wgpu.h"],
  ...LIBS,
];

for (const [src, dest] of COPIES) {
  console.log(`Copying ${src} -> ${dest}`);
  await Bun.spawn(["cp", src, dest]).exited;
}

const DOCS_URL = "https://raw.githubusercontent.com/gpuweb/gpuweb/main/spec/index.bs";
await downloadFile(DOCS_URL, "codegen/webgpu_spec.bs");
