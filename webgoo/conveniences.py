import time
from typing import Optional

from . import bindings as webgoo


def get_adapter(power: webgoo.PowerPreference) -> webgoo.Adapter:
    adapter: list[Optional[webgoo.Adapter]] = [None]

    def adapterCB(status: webgoo.RequestAdapterStatus, gotten: webgoo.Adapter, msg: str):
        print("Got adapter with msg:", msg, ", status:", status.name)
        adapter[0] = gotten

    cb = webgoo.RequestAdapterCallback(adapterCB)

    instance = webgoo.createInstance()
    instance.requestAdapter(
        webgoo.requestAdapterOptions(
            powerPreference=power,
            backendType=webgoo.BackendType.Undefined,
            forceFallbackAdapter=False,
        ),
        cb,
    )

    while adapter[0] is None:
        time.sleep(0.1)

    return adapter[0]


def get_device(adapter: webgoo.Adapter) -> webgoo.Device:
    device: list[Optional[webgoo.Device]] = [None]

    def deviceCB(status: webgoo.RequestDeviceStatus, gotten: webgoo.Device, msg: str):
        print("Got device with msg:", msg, ", status:", status.name)
        device[0] = gotten

    def deviceLostCB(reason: webgoo.DeviceLostReason, msg: str):
        print("Lost device!:", reason, msg)

    dlcb = webgoo.DeviceLostCallback(deviceLostCB)
    cb = webgoo.RequestDeviceCallback(deviceCB)

    adapter.requestDevice(
        webgoo.deviceDescriptor(
            requiredFeatures=[],
            defaultQueue=webgoo.queueDescriptor(),
            deviceLostCallback=dlcb,
        ),
        cb,
    )

    while device[0] is None:
        time.sleep(0.1)

    return device[0]


def _mapped_cb(status):
    print("Mapped?", status.name)
    if status != webgoo.BufferMapAsyncStatus.Success:
        raise RuntimeError(f"Mapping error! {status}")


mapped_cb = webgoo.BufferMapCallback(_mapped_cb)


def read_buffer(device: webgoo.Device, buffer: webgoo.Buffer, offset: int, size: int):
    buffer.mapAsync(
        webgoo.MapModeFlags([webgoo.MapMode.Read]),
        offset=offset,
        size=size,
        callback=mapped_cb,
    )
    device.poll(True, wrappedSubmissionIndex=None)
    # assume we're now mapped? (seems dicey!)
    mapping = buffer.getMappedRange(0, size)
    return mapping.to_bytes()


def read_rgba_texture(device: webgoo.Device, tex: webgoo.Texture, size: tuple[int, int]):
    (w, h) = size
    bytesize = w * h * 4
    # create a staging buffer?
    readbuff = device.createBuffer(
        usage=webgoo.BufferUsageFlags(
            [webgoo.BufferUsage.CopyDst, webgoo.BufferUsage.MapRead]
        ),
        size=bytesize,
        mappedAtCreation=False,
    )
    encoder = device.createCommandEncoder()
    encoder.copyTextureToBuffer(
        source=webgoo.imageCopyTexture(
            texture=tex,
            mipLevel=0,
            origin=webgoo.origin3D(x=0, y=0, z=0),
            aspect=webgoo.TextureAspect.All,
        ),
        destination=webgoo.imageCopyBuffer(
            layout=webgoo.textureDataLayout(offset=0, bytesPerRow=w * 4, rowsPerImage=h),
            buffer=readbuff,
        ),
        copySize=webgoo.extent3D(width=w, height=h, depthOrArrayLayers=1),
    )
    device.getQueue().submit([encoder.finish()])
    return read_buffer(device, readbuff, 0, bytesize)
