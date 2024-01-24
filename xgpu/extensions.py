from typing import Optional, Union

from . import bindings as xg


def _mapped_cb(status):
    print("Mapped?", status.name)
    if status != xg.BufferMapAsyncStatus.Success:
        raise RuntimeError(f"Mapping error! {status}")


mapped_cb = xg.BufferMapCallback(_mapped_cb)


class XDevice(xg.Device):
    def __init__(self, inner: xg.Device):
        super().__init__(inner._cdata)
        self.limits = xg.SupportedLimits()
        self.queue = super().getQueue()

    def getQueue(self) -> xg.Queue:
        # Workaround for reference counting issue with queues in
        # wgpu-native 0.19.1.1
        return self.queue

    def createWGSLShaderModule(
        self, code: str, label: Optional[str] = None
    ) -> xg.ShaderModule:
        return self.createShaderModule(
            nextInChain=xg.ChainedStruct([xg.shaderModuleWGSLDescriptor(code=code)]),
            label=label,
            hints=[],
        )

    def createBufferWithData(
        self, data: bytes, usage: Union[xg.BufferUsage, xg.BufferUsageFlags]
    ) -> xg.Buffer:
        bsize = len(data)
        buffer = self.createBuffer(usage=usage, size=bsize, mappedAtCreation=True)
        range = buffer.getMappedRange(0, bsize)
        range.copy_bytes(data, bsize)
        buffer.unmap()
        return buffer

    def readBuffer(self, buffer: xg.Buffer, offset: int, size: int) -> bytes:
        buffer.mapAsync(
            xg.MapMode.Read,
            offset=offset,
            size=size,
            callback=mapped_cb,
        )
        self.poll(wait=True, wrappedSubmissionIndex=None)
        # TODO: NYI: wgpuBufferGetMapState not implemented (wgpu-native 0.19.1.1)
        # assert buffer.getMapState() == xg.BufferMapState.Mapped, "Buffer is not mapped!"
        mapping = buffer.getMappedRange(0, size)
        res = mapping.to_bytes()
        buffer.unmap()
        return res

    def readRGBATexture(self, tex: xg.Texture) -> bytes:
        (w, h) = (tex.getWidth(), tex.getHeight())
        bytesize = w * h * 4
        # create a staging buffer?
        readbuff = self.createBuffer(
            usage=xg.BufferUsage.CopyDst | xg.BufferUsage.MapRead,
            size=bytesize,
            mappedAtCreation=False,
        )
        encoder = self.createCommandEncoder()
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
        self.getQueue().submit([encoder.finish()])
        return self.readBuffer(readbuff, 0, bytesize)

    def getLimits2(self) -> xg.Limits:
        happy = self.getLimits(self.limits)
        if not happy:
            raise RuntimeError("Failed to get limits.")
        return self.limits.limits


class XSurface(xg.Surface):
    def __init__(self, inner: xg.Surface):
        super().__init__(inner._cdata)
        self.surf_tex = xg.SurfaceTexture()

    def getCurrentTexture2(self) -> xg.SurfaceTexture:
        self.getCurrentTexture(self.surf_tex)
        return self.surf_tex


def bufferLayoutEntry(
    binding: int,
    visibility: Union[xg.ShaderStageFlags, int],
    type: xg.BufferBindingType,
    dynoffset=False,
    minsize=0,
) -> xg.BindGroupLayoutEntry:
    entry = xg.BindGroupLayoutEntry(cdata=None, parent=None)
    entry.binding = binding
    entry.visibility = visibility
    entry.buffer = xg.bufferBindingLayout(
        type=type,
        hasDynamicOffset=dynoffset,
        minBindingSize=minsize,
    )
    return entry


def textureLayoutEntry(
    binding: int,
    visibility: Union[xg.ShaderStageFlags, int],
    sampletype: xg.TextureSampleType,
    viewdim: xg.TextureViewDimension,
    multisampled=False,
) -> xg.BindGroupLayoutEntry:
    entry = xg.BindGroupLayoutEntry(cdata=None, parent=None)
    entry.binding = binding
    entry.visibility = visibility
    entry.texture = xg.textureBindingLayout(
        sampleType=sampletype,
        viewDimension=viewdim,
        multisampled=multisampled,
    )
    return entry


def storageTextureLayoutEntry(
    binding: int,
    visibility: Union[xg.ShaderStageFlags, int],
    format: xg.TextureFormat,
    viewdim: xg.TextureViewDimension,
    access=xg.StorageTextureAccess.WriteOnly,
) -> xg.BindGroupLayoutEntry:
    entry = xg.BindGroupLayoutEntry(cdata=None, parent=None)
    entry.binding = binding
    entry.visibility = visibility
    entry.storageTexture = xg.storageTextureBindingLayout(
        format=format,
        viewDimension=viewdim,
        access=access,
    )
    return entry


def samplerLayoutEntry(
    binding: int,
    visibility: Union[xg.ShaderStageFlags, int],
    type=xg.SamplerBindingType.Filtering,
) -> xg.BindGroupLayoutEntry:
    entry = xg.BindGroupLayoutEntry(cdata=None, parent=None)
    entry.binding = binding
    entry.visibility = visibility
    entry.sampler = xg.samplerBindingLayout(
        type=type,
    )
    return entry
