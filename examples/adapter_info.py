import time


def main():
    import webgoo.conveniences as wgutils

    (adapter, instance) = wgutils.get_adapter()
    adapter.assert_valid()
    features = adapter.enumerateFeatures()
    print("Adapter supported features:")
    for f in features:
        print(f.name)

    _device = wgutils.get_device(adapter)
    _device.assert_valid()
    print("Device supported features:")
    features = _device.enumerateFeatures()
    for f in features:
        print(f.name)

t0 = time.time()
main()
dt = time.time() - t0
print(f"Took: {dt}")
