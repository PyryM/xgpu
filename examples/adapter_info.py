import time
from typing import List


def main():
    import xgpu
    import xgpu.conveniences as xgutils

    def print_features(features: List[xgpu.FeatureName]):
        flist = sorted([f.name for f in features])
        print("Features:", ", ".join(flist))

    def print_limits(limits: xgpu.Limits):
        print("Limits:")
        for k in dir(limits):
            if not k.startswith("_"):
                print(f"{k} -> {getattr(limits, k)}")

    (adapter, instance) = xgutils.get_adapter()
    adapter.assert_valid()
    features = adapter.enumerateFeatures()
    print("========== ADAPTER ==========")
    print_features(features)
    limits = xgpu.SupportedLimits()
    adapter.getLimits(limits)
    print_limits(limits.limits)

    device = xgutils.get_device(adapter)
    device.assert_valid()
    print("========== DEVICE ==========")
    features = device.enumerateFeatures()
    print_features(features)
    device.getLimits(limits)
    print_limits(limits.limits)


t0 = time.time()
main()
dt = time.time() - t0
print(f"Took: {dt}")
