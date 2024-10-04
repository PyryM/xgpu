# ruff: noqa
import os
from typing import List, Optional, Tuple

import glfw
import imgui
import numpy as np
from numpy.typing import NDArray

from .. import bindings as xg
from .glfw_window import GLFWWindow
from .wrappers import BinderBuilder, XDevice, auto_vertex_layout

_assets = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets"))


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


def compute_fb_scale(window_size, frame_buffer_size):
    win_width, win_height = window_size
    fb_width, fb_height = frame_buffer_size

    if win_width > 0 and win_height > 0:
        return fb_width / win_width, fb_height / win_height
    else:
        return 1.0, 1.0


class ImguiWindow(GLFWWindow):
    def __init__(self, w: int, h: int, title="xgpu", font: Optional[str] = None):
        self.io = imgui.get_io()  # type: ignore

        self._add_font(font)

        self._gui_time = None
        super().__init__(w, h, title)

    def _add_font(self, path: Optional[str] = None) -> None:
        """
        Add the fonts in the `xgpu.extensions.assets.fonts` directory.
        """
        if path is None:
            return

        self.io.fonts.clear()
        self.io.font_global_scale = 1

        if not path.lower().endswith(".ttf"):
            raise ValueError(f"Font must be truetype: {path}")
        abspath = os.path.abspath(path)
        self.io.fonts.add_font_from_file_ttf(
            filename=abspath,
            size_pixels=25.0,
            glyph_ranges=self.io.fonts.get_glyph_ranges_latin(),
        )

    def keyboard_callback(self, window, key, scancode, action, mods):
        # perf: local for faster access
        io = self.io

        if action == glfw.PRESS:
            io.keys_down[key] = True
        elif action == glfw.RELEASE:
            io.keys_down[key] = False

        io.key_ctrl = (
            io.keys_down[glfw.KEY_LEFT_CONTROL] or io.keys_down[glfw.KEY_RIGHT_CONTROL]
        )

        io.key_alt = io.keys_down[glfw.KEY_LEFT_ALT] or io.keys_down[glfw.KEY_RIGHT_ALT]

        io.key_shift = (
            io.keys_down[glfw.KEY_LEFT_SHIFT] or io.keys_down[glfw.KEY_RIGHT_SHIFT]
        )

        io.key_super = (
            io.keys_down[glfw.KEY_LEFT_SUPER] or io.keys_down[glfw.KEY_RIGHT_SUPER]
        )

    def char_callback(self, window, char):
        if 0 < char and char < 0x10000:
            self.io.add_input_character(char)

    def resize_callback(self, window, width, height):
        # self.io.display_size = width, height
        pass

    def mouse_callback(self, *args, **kwargs):
        pass

    def scroll_callback(self, window, x_offset, y_offset):
        self.io.mouse_wheel_horizontal = x_offset
        self.io.mouse_wheel = y_offset

    def process_inputs(self):
        io = self.io

        window_size = (self.width, self.height)  # glfw.get_window_size(self.window)
        fb_size = (
            self.phys_width,
            self.phys_height,
        )  # glfw.get_framebuffer_size(self.window)

        io.display_size = (self.width, self.height)  # window_size
        io.display_fb_scale = compute_fb_scale(window_size, fb_size)
        io.delta_time = 1.0 / 60

        if glfw.get_window_attrib(self.window, glfw.FOCUSED):
            io.mouse_pos = glfw.get_cursor_pos(self.window)
        else:
            io.mouse_pos = -1, -1

        io.mouse_down[0] = glfw.get_mouse_button(self.window, 0)
        io.mouse_down[1] = glfw.get_mouse_button(self.window, 1)
        io.mouse_down[2] = glfw.get_mouse_button(self.window, 2)

        current_time = glfw.get_time()

        if self._gui_time is not None:
            self.io.delta_time = current_time - self._gui_time
        else:
            self.io.delta_time = 1.0 / 60.0
        if io.delta_time <= 0.0:
            io.delta_time = 1.0 / 1000.0

        self._gui_time = current_time


class XGPUImguiRenderer:
    """xgpu integration class."""

    def get_shader_src(self, is_srgb: bool) -> str:
        """Return a specialized variant of the shader targeting either
        an srgb or non-srgb render target.
        """

        if is_srgb:
            # ImGui colors are already in srgb, so if the target is srgb
            # we have to do this dance of converting to linear colors
            # which the target will then convert back to srgb on store
            retval = "vec4f(pow(outcolor.rgb, vec3f(2.2)), outcolor.a)"
        else:
            # The target is an undecorated target, which means that
            # the returned color will be stored directly without gamma
            # adjustment
            retval = "outcolor"

        return """
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
            let outcolor = input.color * texcolor;
            return [[RETVAL]];
        }
        """.replace("[[RETVAL]]", retval)

    def __init__(
        self,
        device: XDevice,
        imgui_io,
        tex_format=xg.TextureFormat.BGRA8Unorm,
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
        bb = BinderBuilder(self._device)
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
        is_srgb = "srgb" in self._window_tex_format.name.lower()
        shadersrc = self.get_shader_src(is_srgb)
        self._shader = self._device.createWGSLShaderModule(code=shadersrc)

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

        vertex_layout = auto_vertex_layout(
            [
                xg.VertexFormat.Float32x2,  # Position
                xg.VertexFormat.Float32x2,  # UV
                xg.VertexFormat.Unorm8x4,  # Color
            ]
        )

        self._pipeline = self._device.createRenderPipeline(
            layout=self._pipeline_layout,
            vertex=xg.vertexState(
                module=self._shader,
                entryPoint="vs_main",
                constants=[],
                buffers=[vertex_layout],
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
            print(f"Resizing vbuff -> {vtx_size}")
            self._vbuff = self._device.createBuffer(
                label="vertexbuffer",
                usage=xg.BufferUsage.Vertex | xg.BufferUsage.CopyDst,
                size=max(1024, vtx_size),
            )

        if self._ibuff is None or self._ibuff.getSize() < idx_size:
            print(f"Resizing ibuff -> {idx_size}")
            self._ibuff = self._device.createBuffer(
                label="indexbuffer",
                usage=xg.BufferUsage.Index | xg.BufferUsage.CopyDst,
                size=max(1024, idx_size),
            )

        offsets: list[tuple[int, int]] = []
        ipos = 0
        vpos = 0
        for cmd in command_lists:
            nvrt = cmd.vtx_buffer_size
            nidx = cmd.idx_buffer_size
            vptr = xg.DataPtr(
                xg.ffi.cast("void *", cmd.vtx_buffer_data), nvrt * imgui.VERTEX_SIZE
            )
            iptr = xg.DataPtr(
                xg.ffi.cast("void *", cmd.idx_buffer_data), nidx * imgui.INDEX_SIZE
            )
            self._device.queue.writeBuffer(
                self._vbuff,
                vpos * imgui.VERTEX_SIZE,
                vptr,
            )
            self._device.queue.writeBuffer(self._ibuff, ipos * imgui.INDEX_SIZE, iptr)
            offsets.append((ipos, vpos))
            ipos += nidx
            vpos += nvrt

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

        ortho_projection = np.ascontiguousarray(
            ortho_proj_imgui(display_width, display_height).T
        )
        self._device.queue.writeBuffer(self._ubuff, 0, xg.DataPtr.wrap(ortho_projection))
        ibuff, vbuff, buffer_offsets = self._upload_geometry(draw_data.commands_lists)

        encoder = self._device.createCommandEncoder()

        color_attachment = xg.renderPassColorAttachment(
            view=color_view,
            depthSlice=0,
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
        for commands, offsets in zip(draw_data.commands_lists, buffer_offsets):
            idx_buffer_offset = offsets[0]
            vtx_buffer_offset = offsets[1]

            last_tex_id = None
            for command in commands.commands:
                if command.texture_id != last_tex_id:
                    _tex, view = self._texture_map[command.texture_id]
                    self._bind_uniforms.set(self._ubuff, 0)
                    self._bind_tex.set(view)
                    self._bind_sampler.set(self._sampler)
                    bg = self._binder.create_bindgroup()
                    bgs.append(bg)
                    renderpass.setBindGroup(0, bg, dynamicOffsets=[])
                    last_tex_id = command.texture_id

                x, y, x1, y1 = command.clip_rect
                renderpass.setScissorRect(int(x), int(y), int(x1 - x), int(y1 - y))
                renderpass.drawIndexed(
                    command.elem_count, 1, idx_buffer_offset, vtx_buffer_offset, 0
                )
                idx_buffer_offset += command.elem_count

        renderpass.end()
        self._device.queue.submit([encoder.finish()])
