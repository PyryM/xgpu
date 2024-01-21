import time


def main():
    import wgpu

    def print_props(props):
        print(f"{props['device']} [{props['backend_type']}], {props['description']}")

    def print_features(features):
        flist = sorted([str(f) for f in features])
        print("Features:", ", ".join(flist))

    def print_limits(limits):
        print("Limits:")
        for k in limits:
            print(f"{k} -> {limits[k]}")

    adapter = wgpu.gpu.request_adapter(power_preference="high-performance")
    features = adapter.features
    print("========== ADAPTER ==========")
    print_props(adapter.request_adapter_info())
    print_features(features)
    print_limits(adapter.limits)

    device = adapter.request_device(
        required_limits=adapter.limits, required_features=list(features)
    )
    print("========== DEVICE ==========")
    print_features(device.features)
    print_limits(device.limits)


t0 = time.time()
main()
dt = time.time() - t0
print(f"Took: {dt}")
