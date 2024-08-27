import hashlib
import os
import shutil
import subprocess
import zipfile
from platform import uname
from typing import Optional
from urllib.request import urlopen


def fetch(url: str, sha256: Optional[str] = None) -> bytes:
    """
    A simple standard-library only "fetch remote URL" function.

    Parameters
    ------------
    url
      Location of remote resource.
    sha256
      The SHA256 hash of the resource once retrieved,
      will raise a `ValueError` if the hash doesn't match.

    Returns
    -------------
    data
      Retrieved data.
    """
    data = urlopen(url).read()

    if sha256 is not None:
        hashed = hashlib.sha256(data).hexdigest()
        if hashed != sha256:
            raise ValueError("sha256 hash does not match!")

    return data


def download_file(url: str, local_path: str) -> None:
    """
    Download a remote file and write it to the local file system.

    Parameters
    ------------
    url
      URL to download.
    local_path
      File location to write retrieved data.
    """
    response = fetch(url)
    if len(response) == 0:
        raise Exception(f"404: {url}")
    with open(local_path, "wb") as f:
        f.write(response)
    print(f"Downloaded {len(response)} bytes -> {local_path}")


class Lib:
    def __init__(self, src: str, dest: Optional[str]=None):
        self.src = src
        self.dest = dest
        if self.dest is None:
            self.dest = src


SYSLIBS = {
    "windows": [Lib("wgpu_native.dll"), Lib("wgpu_native.dll.lib", "wgpu_native.lib")],
    "linux": [Lib("libwgpu_native.so")],
    "macos": [],  # special handling!
}

ALIASES = {
    "win32": "windows",
    "darwin": "macos",
    "amd64": "x86_64",
    "x64": "x86_64",
    "arm": "aarch64",
    "arm64": "aarch64",
}


def fix_name(name: str) -> str:
    return ALIASES.get(name, name)


BASE_URL = "https://github.com/gfx-rs/wgpu-native/releases/download/"
VERSION = "22.1.0.1"

SYSNAME = uname().system.lower()
IS_WINDOWS = SYSNAME == "windows" or ("microsoft" in uname().release.lower())
OS = fix_name("windows" if IS_WINDOWS else SYSNAME)
ARCH = fix_name(uname().machine.lower())


def make_url(osname: str, arch: str) -> str:
    return f"{BASE_URL}v{VERSION}/wgpu-{osname}-{arch}-release.zip"


def unzip_to(url: str, dest: str) -> None:
    print(f'Downloading release from: "{url}" -> "{dest}"')
    download_file(url, "wgpu_native.zip")

    with zipfile.ZipFile("wgpu_native.zip", "r") as zip_ref:
        zip_ref.extractall(dest)


UNZIP_PATH = "wgpu_native_unzipped"
INCLUDE_PATH = "xgpu/include"

# make sure the include path exists
os.makedirs(INCLUDE_PATH, exist_ok=True)

if OS != "macos":
    unzip_to(make_url(OS, ARCH), UNZIP_PATH)
else:
    # for macos fetch both arm and x64 versions
    unzip_to(make_url("macos", "x86_64"), UNZIP_PATH)
    unzip_to(make_url("macos", "aarch64"), f"{UNZIP_PATH}_ARM")

LIBS = [
    (f"{UNZIP_PATH}/{lib.src}", f"xgpu/{lib.dest}")
    for lib in SYSLIBS.get(OS, [Lib("libwgpu_native.so")])
]

COPIES = [
    (f"{UNZIP_PATH}/webgpu.h", f"{INCLUDE_PATH}/webgpu.h"),
    (f"{UNZIP_PATH}/wgpu.h", f"{INCLUDE_PATH}/wgpu.h"),
    *LIBS,
]

for src, dest in COPIES:
    print(f"Copying {src} -> {dest}")
    shutil.copy2(src, dest)

if OS == "macos":
    # do some manual dylib wrangling
    print("Merging dylibs...")
    subprocess.run(
        [
            "lipo",
            "-create",
            f"{UNZIP_PATH}/libwgpu_native.dylib",
            f"{UNZIP_PATH}_ARM/libwgpu_native.dylib",
            "-output",
            "xgpu/libwgpu_native.dylib",
        ]
    )

DOCS_URL = "https://raw.githubusercontent.com/gpuweb/gpuweb/main/spec/index.bs"
download_file(DOCS_URL, "codegen/webgpu_spec.bs")
