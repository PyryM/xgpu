from typing import List, Optional, Union

from . import bindings as xg


def _mapped_cb(status):
    if status != xg.BufferMapAsyncStatus.Success:
        raise RuntimeError(f"Mapping error! {status}")


mapped_cb = xg.BufferMapCallback(_mapped_cb)


class XAdapter(xg.Adapter):
    def __init__(self, inner: xg.Adapter):
        """Wrap an Adapter into an XAdapter; invalidates the Adapter object"""
        self._cdata = inner._cdata
        inner.invalidate()
        self.properties = xg.AdapterProperties()
        self.limits = xg.SupportedLimits()

    def getLimits2(self) -> xg.Limits:
        happy = self.getLimits(self.limits)
        if not happy:
            raise RuntimeError("Failed to get limits.")
        return self.limits.limits

    def getProperties2(self) -> xg.AdapterProperties:
        self.getProperties(self.properties)
        return self.properties


class XDevice(xg.Device):
    def __init__(self, inner: Union[xg.Device, "XDevice"]):
        """Wrap a Device into an XDevice; invalidates the Device object"""
        self._cdata = inner._cdata
        inner.invalidate()
        if isinstance(inner, XDevice):
            # TODO: wgpu-native 0.19.1.1
            # Copy limits and queue from parent to avoid ref counting issue
            self.limits = inner.limits
            self.queue = inner.queue
        else:
            self.limits = xg.SupportedLimits()
            self.queue = super().getQueue()

    def getQueue(self) -> xg.Queue:
        # TODO: wgpu-native 0.19.1.1
        # Workaround for reference counting issue with queues
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
        self, data: bytes, usage: Union[xg.BufferUsage, xg.BufferUsageFlags, int]
    ) -> xg.Buffer:
        bsize = len(data)
        buffer = self.createBuffer(usage=usage, size=bsize, mappedAtCreation=True)
        range = buffer.getMappedRange(0, bsize)
        range.copy_bytes(data, bsize)
        buffer.unmap()
        return buffer

    def readBuffer(self, buffer: xg.Buffer, offset: int, size: int) -> bytes:
        """Read a buffer from GPU->CPU; the buffer must have MapRead usage"""
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

    def readBufferStaged(self, buffer: xg.Buffer, offset: int, size: int) -> bytes:
        """Read a buffer from GPU->CPU, using a temporary staging buffer if
        the buffer does not have MapRead usage.
        """
        if xg.BufferUsage.MapRead in buffer.getUsage():
            # no need for staging buffer
            return self.readBuffer(buffer, offset, size)
        staging = self.createBuffer(
            usage=xg.BufferUsage.CopyDst | xg.BufferUsage.MapRead,
            size=size,
            mappedAtCreation=False,
        )
        encoder = self.createCommandEncoder()
        encoder.copyBufferToBuffer(buffer, offset, staging, 0, size)
        self.getQueue().submit([encoder.finish()])
        return self.readBuffer(staging, 0, size)

    def readRawTexture(
        self, tex: xg.Texture, bytesize: int, layout: xg.TextureDataLayout
    ) -> bytes:
        (w, h, d) = (tex.getWidth(), tex.getHeight(), tex.getDepthOrArrayLayers())
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
                layout=layout,
                buffer=readbuff,
            ),
            copySize=xg.extent3D(width=w, height=h, depthOrArrayLayers=d),
        )
        self.getQueue().submit([encoder.finish()])
        return self.readBuffer(readbuff, 0, bytesize)

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
        """Wrap a Surface into an XSurface; invalidates the Surface object"""
        self._cdata = inner._cdata
        inner.invalidate()
        self.surf_tex = xg.SurfaceTexture()

    def getCurrentTexture2(self) -> xg.SurfaceTexture:
        self.getCurrentTexture(self.surf_tex)
        return self.surf_tex


class BindRef:
    def __init__(self, binding: int, visibility: Union[xg.ShaderStageFlags, int]):
        self._ptr = xg.ffi.NULL
        self._binding = binding
        self._layout = xg.BindGroupLayoutEntry(cdata=None, parent=None)
        self._layout.binding = binding
        self._layout.visibility = visibility


class BufferBinding(BindRef):
    def __init__(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        type: xg.BufferBindingType,
        dynoffset=False,
        minsize=0,
    ):
        super().__init__(binding, visibility)
        self._layout.buffer = xg.bufferBindingLayout(
            type=type,
            hasDynamicOffset=dynoffset,
            minBindingSize=minsize,
        )

    def set(self, buffer: xg.Buffer, offset: int = 0, size: Optional[int] = None):
        self._ptr.buffer = buffer._cdata
        self._ptr.offset = offset
        if size is not None:
            self._ptr.size = size
        else:
            self._ptr.size = buffer.getSize()


class TextureBinding(BindRef):
    def __init__(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        sampletype: xg.TextureSampleType,
        viewdim: xg.TextureViewDimension,
        multisampled=False,
    ):
        super().__init__(binding, visibility)
        self._layout.texture = xg.textureBindingLayout(
            sampleType=sampletype,
            viewDimension=viewdim,
            multisampled=multisampled,
        )

    def set(self, textureView: xg.TextureView):
        self._ptr.textureView = textureView._cdata


class StorageTextureBinding(BindRef):
    def __init__(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        format: xg.TextureFormat,
        viewdim: xg.TextureViewDimension,
        access=xg.StorageTextureAccess.WriteOnly,
    ):
        super().__init__(binding, visibility)
        self._layout.storageTexture = xg.storageTextureBindingLayout(
            format=format,
            viewDimension=viewdim,
            access=access,
        )

    def set(self, textureView: xg.TextureView):
        self._ptr.textureView = textureView._cdata


class SamplerBinding(BindRef):
    def __init__(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        type=xg.SamplerBindingType.Filtering,
    ):
        super().__init__(binding, visibility)
        self._layout.sampler = xg.samplerBindingLayout(
            type=type,
        )

    def set(self, sampler: xg.Sampler):
        self._ptr.sampler = sampler._cdata


class Binder:
    def __init__(self, device: xg.Device, entries: List[BindRef]):
        self._device = device
        self.layout = device.createBindGroupLayout(
            entries=[entry._layout for entry in entries]
        )
        self._entries = entries
        self._bind_entries = xg.BindGroupEntryList(items=[], count=len(entries))
        for idx, entry in enumerate(entries):
            ptr = self._bind_entries._ptr[idx]
            ptr.binding = entry._binding
            entry._ptr = ptr

    def create_bindgroup(self) -> xg.BindGroup:
        return self._device.createBindGroup(
            layout=self.layout, entries=self._bind_entries
        )


class BinderBuilder:
    def __init__(self, device: xg.Device):
        self.device = device
        self.entries: List[BindRef] = []

    def add_buffer(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        type: xg.BufferBindingType,
        dynoffset=False,
        minsize=0,
    ) -> BufferBinding:
        entry = BufferBinding(binding, visibility, type, dynoffset, minsize)
        self.entries.append(entry)
        return entry

    def add_texture(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        sampletype: xg.TextureSampleType,
        viewdim: xg.TextureViewDimension,
        multisampled=False,
    ) -> TextureBinding:
        entry = TextureBinding(binding, visibility, sampletype, viewdim, multisampled)
        self.entries.append(entry)
        return entry

    def add_storage_texture(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        format: xg.TextureFormat,
        viewdim: xg.TextureViewDimension,
        access=xg.StorageTextureAccess.WriteOnly,
    ) -> StorageTextureBinding:
        entry = StorageTextureBinding(binding, visibility, format, viewdim, access)
        self.entries.append(entry)
        return entry

    def add_sampler(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        type=xg.SamplerBindingType.Filtering,
    ) -> SamplerBinding:
        entry = SamplerBinding(binding, visibility, type)
        self.entries.append(entry)
        return entry

    def complete(self) -> Binder:
        return Binder(self.device, self.entries)
