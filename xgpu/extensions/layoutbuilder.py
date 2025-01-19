from typing import Dict, Iterable, List, Optional, Union

from .. import bindings as xg


def round_up_to(v: int, align: int) -> int:
    m = v % align
    if m != 0:
        v += align - m
    return v


class TypedBindGroup:
    def __init__(self, inner: xg.BindGroup):
        self.inner = inner


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
        dynoffset: bool = False,
        minsize: int = 0,
    ):
        super().__init__(binding, visibility)
        self._layout.buffer = xg.bufferBindingLayout(
            type=type,
            hasDynamicOffset=dynoffset,
            minBindingSize=minsize,
        )

    def set(self, buffer: xg.Buffer, offset: int = 0, size: Optional[int] = None) -> None:
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
        multisampled: bool = False,
    ):
        super().__init__(binding, visibility)
        self._layout.texture = xg.textureBindingLayout(
            sampleType=sampletype,
            viewDimension=viewdim,
            multisampled=multisampled,
        )

    def set(self, textureView: xg.TextureView) -> None:
        self._ptr.textureView = textureView._cdata


class StorageTextureBinding(BindRef):
    def __init__(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        format: xg.TextureFormat,
        viewdim: xg.TextureViewDimension,
        access: xg.StorageTextureAccess = xg.StorageTextureAccess.WriteOnly,
    ):
        super().__init__(binding, visibility)
        self._layout.storageTexture = xg.storageTextureBindingLayout(
            format=format,
            viewDimension=viewdim,
            access=access,
        )

    def set(self, textureView: xg.TextureView) -> None:
        self._ptr.textureView = textureView._cdata


class SamplerBinding(BindRef):
    def __init__(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        type: xg.SamplerBindingType = xg.SamplerBindingType.Filtering,
    ):
        super().__init__(binding, visibility)
        self._layout.sampler = xg.samplerBindingLayout(
            type=type,
        )

    def set(self, sampler: xg.Sampler) -> None:
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
        dynoffset: bool = False,
        minsize: int = 0,
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
        multisampled: bool = False,
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
        access: xg.StorageTextureAccess = xg.StorageTextureAccess.WriteOnly,
    ) -> StorageTextureBinding:
        entry = StorageTextureBinding(binding, visibility, format, viewdim, access)
        self.entries.append(entry)
        return entry

    def add_sampler(
        self,
        binding: int,
        visibility: Union[xg.ShaderStageFlags, int],
        type: xg.SamplerBindingType = xg.SamplerBindingType.Filtering,
    ) -> SamplerBinding:
        entry = SamplerBinding(binding, visibility, type)
        self.entries.append(entry)
        return entry

    def complete(self) -> Binder:
        return Binder(self.device, self.entries)


VERTEX_FORMAT_SIZES: Dict[xg.VertexFormat, int] = {
    xg.VertexFormat.Uint8x2: 2,
    xg.VertexFormat.Uint8x4: 4,
    xg.VertexFormat.Sint8x2: 2,
    xg.VertexFormat.Sint8x4: 4,
    xg.VertexFormat.Unorm8x2: 2,
    xg.VertexFormat.Unorm8x4: 4,
    xg.VertexFormat.Snorm8x2: 2,
    xg.VertexFormat.Snorm8x4: 4,
    xg.VertexFormat.Uint16x2: 4,
    xg.VertexFormat.Uint16x4: 8,
    xg.VertexFormat.Sint16x2: 4,
    xg.VertexFormat.Sint16x4: 8,
    xg.VertexFormat.Unorm16x2: 4,
    xg.VertexFormat.Unorm16x4: 8,
    xg.VertexFormat.Snorm16x2: 4,
    xg.VertexFormat.Snorm16x4: 8,
    xg.VertexFormat.Float16x2: 4,
    xg.VertexFormat.Float16x4: 8,
    xg.VertexFormat.Float32: 4,
    xg.VertexFormat.Float32x2: 8,
    xg.VertexFormat.Float32x3: 12,
    xg.VertexFormat.Float32x4: 16,
    xg.VertexFormat.Uint32: 4,
    xg.VertexFormat.Uint32x2: 8,
    xg.VertexFormat.Uint32x3: 12,
    xg.VertexFormat.Uint32x4: 16,
    xg.VertexFormat.Sint32: 4,
    xg.VertexFormat.Sint32x2: 8,
    xg.VertexFormat.Sint32x3: 12,
    xg.VertexFormat.Sint32x4: 16,
}


class VertexLayoutBuilder:
    def __init__(
        self,
        stride: Optional[int] = None,
        step_mode: xg.VertexStepMode = xg.VertexStepMode.Vertex,
    ):
        self.attributes: List[xg.VertexAttribute] = []
        self.stride = stride
        self.offset = 0
        self.shader_location = 0
        self.step_mode = step_mode

    def skip_location(self) -> None:
        """Skip a shader location"""
        self.shader_location += 1

    def add_padding(self, pad: int) -> None:
        """Add padding"""
        self.offset += pad

    def align_to(self, align: int) -> None:
        """Add padding so that the next attribute is aligned to a specific byte alignment"""
        self.offset = round_up_to(self.offset, align)

    def add_attribute(self, format: xg.VertexFormat, size: Optional[int] = None) -> None:
        """Add an attribute; if size is not provided it will be inferred from the format"""
        format_size = VERTEX_FORMAT_SIZES.get(format)
        if format_size is None:
            raise ValueError(f"Could not infer size for format {format.name}")
        if size is None:
            size = format_size
        else:
            assert size >= format_size, (
                f"Declared size {size} is smaller than size({format.name}): {format_size}"
            )

        self.attributes.append(
            xg.vertexAttribute(
                format=format,
                offset=self.offset,
                shaderLocation=self.shader_location,
            )
        )
        self.offset += size
        self.shader_location += 1

    def build(self) -> xg.VertexBufferLayout:
        """Produce a vertex buffer layout"""
        if self.stride is not None:
            stride = self.stride
            assert stride >= self.offset, (
                f"Declared stride {stride} is smaller than vertex size {self.offset}"
            )
        else:
            stride = self.offset
        return xg.vertexBufferLayout(
            arrayStride=stride, stepMode=self.step_mode, attributes=self.attributes
        )


def auto_vertex_layout(
    attribs: Iterable[xg.VertexFormat],
    step_mode: xg.VertexStepMode = xg.VertexStepMode.Vertex,
) -> xg.VertexBufferLayout:
    builder = VertexLayoutBuilder()
    for attrib in attribs:
        builder.add_attribute(attrib)
    return builder.build()
