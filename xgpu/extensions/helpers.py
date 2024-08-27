import time
from typing import Callable, List, Optional, Tuple, Union

from .. import bindings as xg
from .wrappers import XAdapter, XDevice, XSurface


def maybe_chain(item: Optional[xg.Chainable] = None) -> Optional[xg.ChainedStruct]:
    if item is None:
        return None
    return xg.ChainedStruct([item])


def enable_logging(
    level: xg.LogLevel, callback: Optional[Callable[[xg.LogLevel, str], None]] = None
) -> None:
    def _log_cb(level: xg.LogLevel, msg: str) -> None:
        print(f"[{level.name}]: {msg}")

    if callback is None:
        callback = _log_cb

    log_cb = xg.LogCallback(callback)
    print("Enabling logging?")
    xg.setLogCallback(log_cb)
    xg.setLogLevel(level)


def get_instance(
    shader_debug: bool = False,
    validation: bool = False,
    backends: Optional[Union[xg.InstanceBackend, xg.InstanceBackendFlags, int]] = None,
) -> xg.Instance:
    extras = None
    if shader_debug or validation or (backends is not None):
        extras = xg.InstanceExtras()
        if shader_debug:
            extras.flags |= xg.InstanceFlag.Debug
        if validation:
            extras.flags |= xg.InstanceFlag.Validation
        if backends is not None:
            extras.backends = backends
    return xg.createInstance(nextInChain=maybe_chain(extras))


def get_adapter(
    instance: Optional[xg.Instance] = None,
    power: xg.PowerPreference = xg.PowerPreference.HighPerformance,
    surface: Optional[xg.Surface] = None,
    timeout: float = 60.0,
) -> Tuple[XAdapter, xg.Instance]:
    """
    Get an adapter, blocking up to `timeout` seconds
    """

    # will be populated by a callback
    stash: List[Optional[Tuple[xg.RequestAdapterStatus, xg.Adapter, str]]] = [None]

    def adapterCB(status: xg.RequestAdapterStatus, adapter: xg.Adapter, msg: str) -> None:
        print("Got adapter with msg:", msg, ", status:", status.name)
        stash[0] = (status, adapter, msg)

    cb = xg.InstanceRequestAdapterCallback(adapterCB)

    if instance is None:
        instance = get_instance()
    instance.requestAdapter(
        xg.requestAdapterOptions(
            powerPreference=power,
            backendType=xg.BackendType.Undefined,
            forceFallbackAdapter=False,
            compatibleSurface=surface,
        ),
        cb,
    )

    deadline = time.time() + timeout
    while stash[0] is None:
        time.sleep(0.1)
        if time.time() > deadline:
            raise TimeoutError(f"Timed out getting adapter after {timeout:0.2f}s!")

    # we have exited the loop without raising
    status, adapter, msg = stash[0]
    stash[0] = None  # avoid keeping around a GC reference!

    if status != xg.RequestAdapterStatus.Success:
        raise RuntimeError(
            f"Failed to get adapter, status=`{status.name}`, message:'{msg}'"
        )

    return XAdapter(adapter), instance


def get_preferred_format(
    adapter: xg.Adapter, surface: xg.Surface, prefer_srgb: bool = True
) -> xg.TextureFormat:
    """
    Pick a texture format compatible with a surface.
    """
    caps = surface.getCapabilities(adapter=adapter)
    assert len(caps.formats) > 0, "Surface has zero supported formats!"
    if prefer_srgb:
        for fmt in caps.formats:
            if fmt.name.endswith("Srgb"):
                return fmt
    return caps.formats[0]


def get_device(
    adapter: xg.Adapter,
    features: Optional[List[xg.FeatureName]] = None,
    limits: Optional[xg.RequiredLimits] = None,
    timeout: float = 60,
) -> XDevice:
    """
    Get a device, blocking up to `timeout` seconds.
    """

    # collect the device from a callback
    stash: List[Optional[Tuple[xg.RequestDeviceStatus, xg.Device, str]]] = [None]

    def deviceCB(status: xg.RequestDeviceStatus, device: xg.Device, msg: str) -> None:
        print("Got device with msg:", msg, ", status:", status.name)

        stash[0] = (status, device, msg)

    def deviceLostCB(reason: xg.DeviceLostReason, msg: str) -> None:
        print("Lost device!:", reason, msg)

    def errorCB(reason: xg.ErrorType, msg: str) -> None:
        print("Uncaptured error!:", reason, msg)

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
            deviceLostCallback=xg.DeviceLostCallback(deviceLostCB),
            uncapturedErrorCallbackInfo=xg.uncapturedErrorCallbackInfo(
                callback=xg.ErrorCallback(errorCB)
            ),
        ),
        xg.AdapterRequestDeviceCallback(deviceCB),
    )

    deadline = time.time() + timeout
    while stash[0] is None:
        time.sleep(0.1)
        if time.time() > deadline:
            raise TimeoutError(f"Timed out getting device after {timeout:0.2f}s!")

    # we have exited the loop without raising
    status, device, msg = stash[0]
    stash[0] = None  # avoid keeping around a GC reference!

    if status != xg.RequestDeviceStatus.Success:
        raise RuntimeError(
            f"Failed to get device, status=`{status.name}`, message:'{msg}'"
        )

    return XDevice(device)


def startup(
    debug: bool = False, surface_src: Optional[Callable[[xg.Instance], XSurface]] = None
) -> Tuple[xg.Instance, XAdapter, XDevice, Optional[XSurface]]:
    """Simplify acquisition of core objects"""
    instance = get_instance(shader_debug=debug, validation=False)
    surface: Optional[XSurface] = None
    if surface_src is not None:
        surface = surface_src(instance)
    adapter, _ = get_adapter(instance, xg.PowerPreference.HighPerformance, surface)
    device = get_device(adapter)
    return instance, adapter, device, surface


def create_default_view(tex: xg.Texture) -> xg.TextureView:
    return tex.createView(
        format=xg.TextureFormat.Undefined,
        dimension=xg.TextureViewDimension.Undefined,
        mipLevelCount=tex.getMipLevelCount(),
        arrayLayerCount=tex.getDepthOrArrayLayers(),
    )
