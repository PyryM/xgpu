function listFeatures(raw_ffi_func: string): string[] {
  return [
    'def enumerateFeatures(self) -> List["FeatureName"]:',
    `    # Hand-written because of idiosyncratic convention for using this function`,
    `    feature_count = lib.${raw_ffi_func}(self._cdata, ffi.NULL)`,
    `    feature_list = ffi.new("WGPUFeatureName[]", feature_count)`,
    `    lib.${raw_ffi_func}(self._cdata, feature_list)`,
    `    return [FeatureName(feature_list[idx]) for idx in range(feature_count)]`,
  ];
}

const wgpuAdapterEnumerateFeatures = listFeatures(
  "wgpuAdapterEnumerateFeatures"
);
const wgpuDeviceEnumerateFeatures = listFeatures("wgpuDeviceEnumerateFeatures");

export const PATCHED_FUNCTIONS: Map<string, string[]> = new Map([
  ["wgpuAdapterEnumerateFeatures", wgpuAdapterEnumerateFeatures],
  ["wgpuDeviceEnumerateFeatures", wgpuDeviceEnumerateFeatures],
]);

export const BAD_FUNCTIONS: Map<string, string> = new Map([
  ["wgpuAdapterEnumerateFeatures", "This is unsafe. Use hasFeature."],
  ["wgpuDeviceEnumerateFeatures", "This is unsafe. Use hasFeature."],
  ["wgpuGetProcAddress", "Untyped function pointer return."],
]);
