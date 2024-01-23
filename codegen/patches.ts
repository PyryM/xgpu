import { pyList } from "./pygen";

function listFeatures(className: string): string[] {
  const rawFFIFunc = `wgpu${className}EnumerateFeatures`;
  return [
    'def enumerateFeatures(self) -> List["FeatureName"]:',
    `    # Hand-written because of idiosyncratic convention for using this function`,
    `    feature_count = lib.${rawFFIFunc}(self._cdata, ffi.NULL)`,
    `    feature_list = ffi.new("WGPUFeatureName[]", feature_count)`,
    `    lib.${rawFFIFunc}(self._cdata, feature_list)`,
    `    return [FeatureName(feature_list[idx]) for idx in range(feature_count)]`,
  ];
}

function commentedOut(name: string, msg: string): string[] {
  return [`# ${name}: ${msg}`, `# def ${name}(...):`, ``];
}

export const FORCE_NULLABLE_ARGS: Set<string> = new Set([
  "wrappedSubmissionIndex",
]);

const SURFACE_CAPS = `
class SurfaceCapabilities:
    def __init__(self, formats: ${pyList("TextureFormat")}, presentModes: ${pyList("PresentMode")}, alphaModes: ${pyList("CompositeAlphaMode")}):
        self.formats = formats
        self.presentModes = presentModes
        self.alphaModes = alphaModes
`.trim();

export const PATCHED_CLASSES: Map<string, string> = new Map([
  ["WGPUSurfaceCapabilities", SURFACE_CAPS],
]);

const SURFACE_GET_CAPS = `
def getCapabilities(self, adapter: "Adapter") -> "SurfaceCapabilities":
    # Hand-written because the usage pattern for this is ridiculous
    # (it sets raw pointers onto a struct you provide, and you're
    #  expected to free these arrays with a special function)
    caps = ffi.new("WGPUSurfaceCapabilities *")
    lib.wgpuSurfaceGetCapabilities(self._cdata, adapter._cdata, caps)
    formats = [TextureFormat(caps.formats[idx]) for idx in range(caps.formatCount)]
    present_modes = [PresentMode(caps.presentModes[idx]) for idx in range(caps.presentModeCount)]
    alpha_modes = [CompositeAlphaMode(caps.alphaModes[idx]) for idx in range(caps.alphaModeCount)]
    # Note! This free function takes the caps struct *by value*, hence
    # the usage of caps[0] to 'dereference' it. Yes this is weird!
    lib.wgpuSurfaceCapabilitiesFreeMembers(caps[0])
    return SurfaceCapabilities(formats, present_modes, alpha_modes)
`
  .trim()
  .split("\n");

export const PATCHED_FUNCTIONS: Map<string, string[]> = new Map([
  ["wgpuAdapterEnumerateFeatures", listFeatures("Adapter")],
  ["wgpuDeviceEnumerateFeatures", listFeatures("Device")],
  ["wgpuSurfaceGetCapabilities", SURFACE_GET_CAPS],
  [
    "wgpuSurfaceCapabilitiesFreeMembers",
    commentedOut("FreeMembers", "Not needed"),
  ],
]);
