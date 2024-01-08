import time
from typing import Optional

from . import bindings as wg


def get_adapter(
    instance: Optional[wg.Instance] = None,
    power=wg.PowerPreference.HighPerformance,
    surface: Optional[wg.Surface] = None,
) -> tuple[wg.Adapter, wg.Instance]:
    adapter: list[Optional[wg.Adapter]] = [None]

    def adapterCB(status: wg.RequestAdapterStatus, gotten: wg.Adapter, msg: str):
        print("Got adapter with msg:", msg, ", status:", status.name)
        adapter[0] = gotten

    cb = wg.RequestAdapterCallback(adapterCB)

    if instance is None:
        instance = wg.createInstance()
    instance.requestAdapter(
        wg.requestAdapterOptions(
            powerPreference=power,
            backendType=wg.BackendType.Undefined,
            forceFallbackAdapter=False,
            compatibleSurface=surface,
        ),
        cb,
    )

    while adapter[0] is None:
        time.sleep(0.1)

    return (adapter[0], instance)


def get_device(
    adapter: wg.Adapter, features: Optional[list[wg.FeatureName]] = None
) -> wg.Device:
    device: list[Optional[wg.Device]] = [None]

    def deviceCB(status: wg.RequestDeviceStatus, gotten: wg.Device, msg: str):
        print("Got device with msg:", msg, ", status:", status.name)
        device[0] = gotten

    def deviceLostCB(reason: wg.DeviceLostReason, msg: str):
        print("Lost device!:", reason, msg)

    dlcb = wg.DeviceLostCallback(deviceLostCB)
    cb = wg.RequestDeviceCallback(deviceCB)
    if features is None:
        features = adapter.enumerateFeatures()

    adapter.requestDevice(
        wg.deviceDescriptor(
            requiredFeatures=features,
            defaultQueue=wg.queueDescriptor(),
            deviceLostCallback=dlcb,
        ),
        cb,
    )

    while device[0] is None:
        time.sleep(0.1)

    return device[0]


def _mapped_cb(status):
    print("Mapped?", status.name)
    if status != wg.BufferMapAsyncStatus.Success:
        raise RuntimeError(f"Mapping error! {status}")


mapped_cb = wg.BufferMapCallback(_mapped_cb)


def read_buffer(device: wg.Device, buffer: wg.Buffer, offset: int, size: int):
    buffer.mapAsync(
        wg.MapModeFlags([wg.MapMode.Read]),
        offset=offset,
        size=size,
        callback=mapped_cb,
    )
    device.poll(True, wrappedSubmissionIndex=None)
    # assume we're now mapped? (seems dicey!)
    mapping = buffer.getMappedRange(0, size)
    return mapping.to_bytes()


def read_rgba_texture(device: wg.Device, tex: wg.Texture):
    (w, h) = (tex.getWidth(), tex.getHeight())
    bytesize = w * h * 4
    # create a staging buffer?
    readbuff = device.createBuffer(
        usage=wg.BufferUsageFlags([wg.BufferUsage.CopyDst, wg.BufferUsage.MapRead]),
        size=bytesize,
        mappedAtCreation=False,
    )
    encoder = device.createCommandEncoder()
    encoder.copyTextureToBuffer(
        source=wg.imageCopyTexture(
            texture=tex,
            mipLevel=0,
            origin=wg.origin3D(x=0, y=0, z=0),
            aspect=wg.TextureAspect.All,
        ),
        destination=wg.imageCopyBuffer(
            layout=wg.textureDataLayout(offset=0, bytesPerRow=w * 4, rowsPerImage=h),
            buffer=readbuff,
        ),
        copySize=wg.extent3D(width=w, height=h, depthOrArrayLayers=1),
    )
    device.getQueue().submit([encoder.finish()])
    return read_buffer(device, readbuff, 0, bytesize)
