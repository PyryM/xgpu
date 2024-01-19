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

export const FORCE_NULLABLE_ARGS: Set<string> = new Set([
  "wrappedSubmissionIndex",
]);

export const PATCHED_FUNCTIONS: Map<string, string[]> = new Map([
  ["wgpuAdapterEnumerateFeatures", listFeatures("Adapter")],
  ["wgpuDeviceEnumerateFeatures", listFeatures("Device")]
]);

