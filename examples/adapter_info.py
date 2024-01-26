import time
from typing import List


def main():
    import xgpu
    import xgpu.conveniences as xgutils

    def print_props(props: xgpu.AdapterProperties):
        print(f"{props.name} [{props.backendType.name}], {props.driverDescription}")

    def print_features(features: List[xgpu.FeatureName]):
        flist = sorted([f.name for f in features])
        print("Features:", ", ".join(flist))

    def print_limits(limits: xgpu.Limits):
        print("Limits:")
        for k in dir(limits):
            if not k.startswith("_"):
                print(f"{k} -> {getattr(limits, k)}")

    (adapter, instance) = xgutils.get_adapter()
    assert adapter.isValid(), "Failed to get adapter"
    features = adapter.enumerateFeatures()
    print("========== ADAPTER ==========")
    print_props(adapter.getProperties2())
    print_features(features)
    print_limits(adapter.getLimits2())

    device = xgutils.get_device(adapter)
    assert device.isValid(), "Failed to get device"
    print("========== DEVICE ==========")
    features = device.enumerateFeatures()
    print_features(features)
    print_limits(device.getLimits2())


t0 = time.time()
main()
dt = time.time() - t0
print(f"Took: {dt}")
