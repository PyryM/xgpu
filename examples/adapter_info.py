import time
from typing import List


def main():
    import xgpu
    import xgpu.extensions.helpers as xgutils

    def print_props(props: xgpu.AdapterInfo):
        print(f"{props.device} [{props.backendType.name}], {props.description}")

    def print_features(features: List[xgpu.FeatureName]):
        flist = sorted([f.name for f in features])
        print("Features:", ", ".join(flist))

    def print_limits(limits: xgpu.Limits):
        print("Limits:")
        for k in dir(limits):
            if not k.startswith("_"):
                print(f"{k} -> {getattr(limits, k)}")

    (adapter, instance) = xgutils.get_adapter()
    features = adapter.enumerateFeatures()
    print("========== ADAPTER ==========")
    print_props(adapter.getInfo2())
    print_features(features)
    print_limits(adapter.getLimits2())

    device = xgutils.get_device(adapter)
    print("========== DEVICE ==========")
    features = device.enumerateFeatures()
    print_features(features)
    print_limits(device.getLimits2())


t0 = time.time()
main()
dt = time.time() - t0
print(f"Took: {dt}")
