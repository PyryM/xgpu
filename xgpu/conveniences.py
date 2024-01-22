import time
from typing import Optional

from . import bindings as xg


def get_adapter(
    instance: Optional[xg.Instance] = None,
    power=xg.PowerPreference.HighPerformance,
    surface: Optional[xg.Surface] = None,
) -> tuple[xg.Adapter, xg.Instance]:
    adapter: list[Optional[xg.Adapter]] = [None]

    def adapterCB(status: xg.RequestAdapterStatus, gotten: xg.Adapter, msg: str):
        print("Got adapter with msg:", msg, ", status:", status.name)
        adapter[0] = gotten

    cb = xg.RequestAdapterCallback(adapterCB)

    if instance is None:
        instance = xg.createInstance()
    instance.requestAdapter(
        xg.requestAdapterOptions(
            powerPreference=power,
            backendType=xg.BackendType.Undefined,
            forceFallbackAdapter=False,
            compatibleSurface=surface,
        ),
        cb,
    )

    while adapter[0] is None:
        time.sleep(0.1)

    return (adapter[0], instance)


def get_device(
    adapter: xg.Adapter,
    features: Optional[list[xg.FeatureName]] = None,
    limits: Optional[xg.RequiredLimits] = None,
) -> xg.Device:
    device: list[Optional[xg.Device]] = [None]

    def deviceCB(status: xg.RequestDeviceStatus, gotten: xg.Device, msg: str):
        print("Got device with msg:", msg, ", status:", status.name)
        device[0] = gotten

    def deviceLostCB(reason: xg.DeviceLostReason, msg: str):
        print("Lost device!:", reason, msg)

    dlcb = xg.DeviceLostCallback(deviceLostCB)
    cb = xg.RequestDeviceCallback(deviceCB)
    if features is None:
        print("Requesting all available features")
        features = adapter.enumerateFeatures()

    if limits is None:
        print("Requesting maximal supported limits")
        supported = xg.SupportedLimits()
        adapter.getLimits(supported)
        limits = xg.requiredLimits(limits=supported.limits)

    adapter.requestDevice(
        xg.deviceDescriptor(
            requiredFeatures=features,
            requiredLimits=limits,
            defaultQueue=xg.queueDescriptor(),
            deviceLostCallback=dlcb,
        ),
        cb,
    )

    while device[0] is None:
        time.sleep(0.1)

    return device[0]
