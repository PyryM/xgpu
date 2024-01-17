import time
from typing import Optional, Union

from . import bindings as xg
from ._wgpu_native_cffi import ffi


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
    adapter: xg.Adapter, features: Optional[list[xg.FeatureName]] = None
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
        features = adapter.enumerateFeatures()

    adapter.requestDevice(
        xg.deviceDescriptor(
            requiredFeatures=features,
            defaultQueue=xg.queueDescriptor(),
            deviceLostCallback=dlcb,
        ),
        cb,
    )

    while device[0] is None:
        time.sleep(0.1)

    return device[0]


def _mapped_cb(status):
    print("Mapped?", status.name)
    if status != xg.BufferMapAsyncStatus.Success:
        raise RuntimeError(f"Mapping error! {status}")


mapped_cb = xg.BufferMapCallback(_mapped_cb)


def read_buffer(device: xg.Device, buffer: xg.Buffer, offset: int, size: int):
    buffer.mapAsync(
        xg.MapMode.Read,
        offset=offset,
        size=size,
        callback=mapped_cb,
    )
    device.poll(True, wrappedSubmissionIndex=None)
    # assume we're now mapped? (seems dicey!)
    mapping = buffer.getMappedRange(0, size)
    res = mapping.to_bytes()
    buffer.unmap()
    return res


def read_rgba_texture(device: xg.Device, tex: xg.Texture):
    (w, h) = (tex.getWidth(), tex.getHeight())
    bytesize = w * h * 4
    # create a staging buffer?
    readbuff = device.createBuffer(
        usage=xg.BufferUsage.CopyDst | xg.BufferUsage.MapRead,
        size=bytesize,
        mappedAtCreation=False,
    )
    encoder = device.createCommandEncoder()
    encoder.copyTextureToBuffer(
        source=xg.imageCopyTexture(
            texture=tex,
            mipLevel=0,
            origin=xg.origin3D(x=0, y=0, z=0),
            aspect=xg.TextureAspect.All,
        ),
        destination=xg.imageCopyBuffer(
            layout=xg.textureDataLayout(offset=0, bytesPerRow=w * 4, rowsPerImage=h),
            buffer=readbuff,
        ),
        copySize=xg.extent3D(width=w, height=h, depthOrArrayLayers=1),
    )
    device.getQueue().submit([encoder.finish()])
    return read_buffer(device, readbuff, 0, bytesize)


def create_buffer_with_data(
    device: xg.Device, data: bytes, usage: Union[xg.BufferUsage, xg.BufferUsageFlags]
) -> xg.Buffer:
    bsize = len(data)
    buffer = device.createBuffer(usage=usage, size=bsize, mappedAtCreation=True)
    range = buffer.getMappedRange(0, bsize)
    ffi.memmove(range._ptr, data, bsize)
    buffer.unmap()
    return buffer
