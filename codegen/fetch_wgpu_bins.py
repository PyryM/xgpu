import os
import shutil
import zipfile
from platform import uname

import requests


def download_file(url, local_path):
    resp = requests.get(url)
    if resp.status_code == 404:
        raise Exception(f"404: {url}")
    with open(local_path, "wb") as f:
        f.write(resp.content)
    print(f"Downloaded {os.path.getsize(local_path)} bytes -> {local_path}")


class Lib:
    def __init__(self, src, dest=None):
        self.src = src
        self.dest = dest
        if self.dest is None:
            self.dest = src


SYSLIBS = {
    "windows": [Lib("wgpu_native.dll"), Lib("wgpu_native.dll.lib", "wgpu_native.lib")],
    "linux": [Lib("libwgpu_native.so")],
    "macos": [Lib("libwgpu_native.dylib")],
}

ALIASES = {
    "win32": "windows",
    "darwin": "macos",
    "amd64": "x86_64",
    "x64": "x86_64",
    "arm": "aarch64",
    "arm64": "aarch64",
}


def fix_name(name):
    return ALIASES.get(name, name)


BASE_URL = "https://github.com/gfx-rs/wgpu-native/releases/download/"
VERSION = "0.18.1.4"

SYSNAME = uname().system.lower()
IS_WINDOWS = SYSNAME == "windows" or ("microsoft" in uname().release.lower())
OS = "windows" if IS_WINDOWS else SYSNAME
ARCH = fix_name(uname().machine.lower())
URL = f"{BASE_URL}v{VERSION}/wgpu-{OS}-{ARCH}-release.zip"

UNZIP_PATH = "wgpu_native_unzipped"

print(f'Downloading release from: "{URL}"')
download_file(URL, "wgpu_native.zip")

with zipfile.ZipFile("wgpu_native.zip", "r") as zip_ref:
    zip_ref.extractall(UNZIP_PATH)

LIBS = [
    (f"{UNZIP_PATH}/{lib.src}", f"webgoo/{lib.dest}")
    for lib in SYSLIBS.get(OS, [Lib("libwgpu_native.so")])
]

COPIES = [
    (f"{UNZIP_PATH}/webgpu.h", "webgoo/include/webgpu.h"),
    (f"{UNZIP_PATH}/wgpu.h", "webgoo/include/wgpu.h"),
    *LIBS,
]

for src, dest in COPIES:
    print(f"Copying {src} -> {dest}")
    shutil.copy2(src, dest)

DOCS_URL = "https://raw.githubusercontent.com/gpuweb/gpuweb/main/spec/index.bs"
download_file(DOCS_URL, "codegen/webgpu_spec.bs")
