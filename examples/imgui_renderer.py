from typing import List, Tuple

import imgui
import numpy as np
from numpy.typing import NDArray

import xgpu as xg


def ortho_proj_imgui(px_width: float, px_height: float) -> NDArray:
    return np.array(
        [
            [2.0 / px_width, 0.0, 0.0, -1.0],
            [0.0, -2.0 / px_height, 0.0, 1.0],
            [0.0, 0.0, -1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


class XGPUImguiRenderer:
    """xgpu integration class."""

    SHADER_SRC = """
    struct Uniforms {
        @align(16) proj_mtx: mat4x4f,
    }

    struct VertexInput {
        @location(0) position: vec2f,
        @location(1) uv: vec2f,
        @location(2) color: vec4f,
    }

    struct VertexOutput {
        @builtin(position) position: vec4f,
        @location(0) uv: vec2f,
        @location(1) color: vec4f,
    }

    @group(0) @binding(0) var<uniform> uniforms: Uniforms;
    @group(0) @binding(1) var tex: texture_2d<f32>;
    @group(0) @binding(2) var samp: sampler;

    @vertex
    fn vs_main(input: VertexInput) -> VertexOutput {
        let pos = uniforms.proj_mtx * vec4f(input.position, 0.0, 1.0);
        return VertexOutput(pos, input.uv, input.color);
    }

    @fragment
    fn fs_main(input: VertexOutput) -> @location(0) vec4f {
        let texcolor = textureSample(tex, samp, input.uv.xy);
        return input.color * texcolor;
    }
    """

    def __init__(
        self, device: xg.extensions.XDevice, imgui_io, tex_format=xg.TextureFormat.BGRA8Unorm
    ):
        self._device = device
        self._window_tex_format = tex_format

        self._font_texture: xg.Texture | None = None
        self._font_texture_id: int | None = None

        self._next_tex_id = 0
        self._texture_map: dict[int, tuple[xg.Texture, xg.TextureView]] = {}

        self.io = imgui_io
        self.io.delta_time = 1.0 / 60.0

        self._create_device_objects()
        self.refresh_font_texture()

    def _insert_tex(self, tex: xg.Texture) -> int:
        id = self._next_tex_id
        self._next_tex_id += 1
        self._replace_tex(id, tex)
        return id

    def _replace_tex(self, id: int, tex: xg.Texture):
        view = tex.createView(
            format=xg.TextureFormat.Undefined,
            dimension=xg.TextureViewDimension.Undefined,
            mipLevelCount=1,
            arrayLayerCount=1,
        )
        self._texture_map[id] = (tex, view)

    def refresh_font_texture(self):
        width, height, pixels = self.io.fonts.get_tex_data_as_rgba32()
        self._font_texture = self._device.createTexture(
            label="font",
            usage=xg.TextureUsage.CopyDst | xg.TextureUsage.TextureBinding,
            dimension=xg.TextureDimension._2D,
            size=xg.extent3D(width=width, height=height, depthOrArrayLayers=1),
            format=xg.TextureFormat.RGBA8Unorm,
            viewFormats=[xg.TextureFormat.RGBA8Unorm],
        )

        if self._font_texture_id is None:
            self._font_texture_id = self._insert_tex(self._font_texture)
        else:
            self._replace_tex(self._font_texture_id, self._font_texture)

        self._device.queue.writeTexture(
            xg.imageCopyTexture(
                texture=self._font_texture,
                mipLevel=0,
                origin=xg.origin3D(x=0, y=0, z=0),
                aspect=xg.TextureAspect.All,
            ),
            data=xg.DataPtr.wrap(pixels),
            dataLayout=xg.textureDataLayout(
                offset=0, bytesPerRow=width * 4, rowsPerImage=height
            ),
            writeSize=xg.extent3D(width=width, height=height, depthOrArrayLayers=1),
        )

        self.io.fonts.texture_id = self._font_texture_id
        self.io.fonts.clear_tex_data()

    def _create_bind_layout(self):
        # @group(0) @binding(0) var<uniform> uniforms: Uniforms;
        # @group(0) @binding(1) var tex: texture_2d<f32>;
        # @group(0) @binding(2) var samp: sampler;
        bb = xg.extensions.BinderBuilder(self._device)
        self._bind_uniforms = bb.add_buffer(
            binding=0,
            visibility=xg.ShaderStage.Vertex,
            type=xg.BufferBindingType.Uniform,
        )
        self._bind_tex = bb.add_texture(
            binding=1,
            visibility=xg.ShaderStage.Fragment,
            sampletype=xg.TextureSampleType.Float,
            viewdim=xg.TextureViewDimension._2D,
        )
        self._bind_sampler = bb.add_sampler(binding=2, visibility=xg.ShaderStage.Fragment)
        self._binder = bb.complete()

    def _create_device_objects(self):
        self._create_bind_layout()
        self._shader = self._device.createWGSLShaderModule(code=self.SHADER_SRC)

        self._pipeline_layout = self._device.createPipelineLayout(
            bindGroupLayouts=[self._binder.layout]
        )
        self._ubuff = self._device.createBuffer(
            usage=xg.BufferUsage.CopyDst | xg.BufferUsage.Uniform, size=64
        )

        self._sampler = self._device.createSampler(
            minFilter=xg.FilterMode.Linear,
            magFilter=xg.FilterMode.Linear,
            mipmapFilter=xg.MipmapFilterMode.Linear,
            compare=xg.CompareFunction.Undefined,
        )

        self._vbuff: xg.Buffer | None = None
        self._ibuff: xg.Buffer | None = None

        REPLACE = xg.blendComponent(
            srcFactor=xg.BlendFactor.One,
            dstFactor=xg.BlendFactor.Zero,
            operation=xg.BlendOperation.Add,
        )
        BLEND = xg.blendComponent(
            srcFactor=xg.BlendFactor.SrcAlpha,
            dstFactor=xg.BlendFactor.OneMinusSrcAlpha,
            operation=xg.BlendOperation.Add,
        )
        primitive = xg.primitiveState(
            topology=xg.PrimitiveTopology.TriangleList,
            stripIndexFormat=xg.IndexFormat.Undefined,
            frontFace=xg.FrontFace.CW,
            cullMode=xg.CullMode._None,
        )
        color_target = xg.colorTargetState(
            format=self._window_tex_format,
            blend=xg.blendState(color=BLEND, alpha=REPLACE),
            writeMask=xg.ColorWriteMask.All,
        )

        self._pipeline = self._device.createRenderPipeline(
            layout=self._pipeline_layout,
            vertex=xg.vertexState(
                module=self._shader,
                entryPoint="vs_main",
                constants=[],
                buffers=[
                    xg.vertexBufferLayout(
                        arrayStride=imgui.VERTEX_SIZE,
                        stepMode=xg.VertexStepMode.Vertex,
                        attributes=[
                            xg.vertexAttribute(
                                format=xg.VertexFormat.Float32x2,
                                offset=0,
                                shaderLocation=0,
                            ),
                            xg.vertexAttribute(
                                format=xg.VertexFormat.Float32x2,
                                offset=8,
                                shaderLocation=1,
                            ),
                            xg.vertexAttribute(
                                format=xg.VertexFormat.Unorm8x4,
                                offset=16,
                                shaderLocation=2,
                            ),
                        ],
                    ),
                ],
            ),
            primitive=primitive,
            multisample=xg.multisampleState(),
            fragment=xg.fragmentState(
                module=self._shader,
                entryPoint="fs_main",
                constants=[],
                targets=[color_target],
            ),
        )
        assert self._pipeline.isValid(), "Failed to create pipeline!"

    def _upload_geometry(
        self, command_lists
    ) -> Tuple[xg.Buffer, xg.Buffer, List[Tuple[int, int]]]:
        # Merge all the command buffer vertex+index lists into
        # a single vertex buffer and single index buffer
        idx_count = sum(cmd.idx_buffer_size for cmd in command_lists)
        vtx_count = sum(cmd.vtx_buffer_size for cmd in command_lists)

        idx_size = idx_count * imgui.INDEX_SIZE
        vtx_size = vtx_count * imgui.VERTEX_SIZE

        if self._vbuff is None or self._vbuff.getSize() < vtx_size:
            self._vbuff = self._device.createBuffer(
                label="vertexbuffer",
                usage=xg.BufferUsage.Vertex | xg.BufferUsage.CopyDst,
                size=max(1024, vtx_size),
            )

        if self._ibuff is None or self._ibuff.getSize() < idx_size:
            self._ibuff = self._device.createBuffer(
                label="indexbuffer",
                usage=xg.BufferUsage.Index | xg.BufferUsage.CopyDst,
                size=max(1024, idx_size),
            )

        offsets: list[tuple[int, int]] = []
        ipos = 0
        vpos = 0
        for cmd in command_lists:
            vptr = xg.DataPtr(xg.ffi.cast("void *", cmd.vtx_buffer_data), vtx_size)
            iptr = xg.DataPtr(xg.ffi.cast("void *", cmd.idx_buffer_data), idx_size)
            self._device.queue.writeBuffer(
                self._vbuff,
                vpos * imgui.VERTEX_SIZE,
                vptr,
            )
            self._device.queue.writeBuffer(
                self._ibuff, ipos * imgui.INDEX_SIZE, iptr
            )
            offsets.append((ipos, vpos))
            ipos += cmd.idx_buffer_size
            vpos += cmd.vtx_buffer_size

        return self._ibuff, self._vbuff, offsets

    def render(self, draw_data, color_view: xg.TextureView):
        # perf: local for faster access
        io = self.io

        display_width, display_height = io.display_size
        fb_width = int(display_width * io.display_fb_scale[0])
        fb_height = int(display_height * io.display_fb_scale[1])

        if fb_width == 0 or fb_height == 0:
            return

        draw_data.scale_clip_rects(*io.display_fb_scale)

        ortho_projection = np.ascontiguousarray(ortho_proj_imgui(display_width, display_height).T)
        self._device.queue.writeBuffer(self._ubuff, 0, xg.DataPtr.wrap(ortho_projection))
        ibuff, vbuff, buffer_offsets = self._upload_geometry(draw_data.commands_lists)

        encoder = self._device.createCommandEncoder()

        color_attachment = xg.renderPassColorAttachment(
            view=color_view,
            loadOp=xg.LoadOp.Load,
            storeOp=xg.StoreOp.Store,
            clearValue=xg.Color(),
        )

        renderpass = encoder.beginRenderPass(colorAttachments=[color_attachment])
        renderpass.setPipeline(self._pipeline)
        renderpass.setVertexBuffer(0, vbuff, 0, vbuff.getSize())
        ifmt = xg.IndexFormat.Uint16
        if imgui.INDEX_SIZE == 4:
            ifmt = xg.IndexFormat.Uint32
        renderpass.setIndexBuffer(ibuff, ifmt, 0, ibuff.getSize())

        bgs = []
        for commands in draw_data.commands_lists:
            idx_buffer_offset = 0

            # todo: allow to iterate over _CmdList
            last_tex_id = None
            for command, offsets in zip(commands.commands, buffer_offsets):
                if command.texture_id != last_tex_id:
                    _tex, view = self._texture_map[command.texture_id]
                    self._bind_uniforms.set(self._ubuff, 0)
                    self._bind_tex.set(view)
                    self._bind_sampler.set(self._sampler)
                    bg = self._binder.create_bindgroup()
                    bgs.append(bg)
                    renderpass.setBindGroup(0, bg, dynamicOffsets=[])
                    last_tex_id = command.texture_id

                x, y, z, w = command.clip_rect
                renderpass.setScissorRect(
                    int(x), int(fb_height - w), int(z - x), int(w - y)
                )
                renderpass.drawIndexed(
                    command.elem_count, 1, offsets[0] + idx_buffer_offset, offsets[1], 0
                )

                idx_buffer_offset += command.elem_count * imgui.INDEX_SIZE

        renderpass.end()
        self._device.queue.submit([encoder.finish()])

