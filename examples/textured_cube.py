"""
Textured cube
"""

import math
from typing import List, Tuple

import numpy as np
import trimesh
from example_utils import proj_perspective
from numpy.typing import NDArray

import xgpu as xg
from xgpu.extensions import (
    BinderBuilder,
    XDevice,
    auto_vertex_layout,
    get_preferred_format,
)
from xgpu.extensions.glfw_window import GLFWWindow
from xgpu.extensions.ktx import open_ktx
from xgpu.extensions.standardimage import open_image
from xgpu.extensions.texloader import TextureData


def set_transform(
    target: NDArray, rot: Tuple[float, float, float], scale: float, pos: NDArray
) -> None:
    # Note: webgpu expects column-major array order
    r = trimesh.transformations.euler_matrix(rot[0], rot[1], rot[2])
    target[0:3, 0:3] = r[0:3, 0:3].T * scale
    target[3, 0:3] = pos
    target[3, 3] = 1.0


def get_source(is_srgb: bool) -> str:
    if is_srgb:
        outcolor = "let outcolor = pow(texcolor.rgb, vec3f(2.2));"
    else:
        outcolor = "let outcolor = texcolor.rgb;"

    return """
    struct Uniforms {
    @align(16) view_proj_mat: mat4x4f,
    @align(16) model_mat: mat4x4f,
    @align(16) color: vec4f,
    }
    @group(0) @binding(0) var<uniform> uniforms: Uniforms;
    @group(0) @binding(1) var tex: texture_2d<f32>;
    @group(0) @binding(2) var samp: sampler;

    struct VertexInput {
        @location(0) pos: vec4f,
        @location(1) uv: vec2f,
    };
    struct VertexOutput {
        @builtin(position) pos: vec4f,
        @location(0) color : vec4f,
        @location(1) uv : vec2f,
    };
    @vertex
    fn vs_main(in: VertexInput) -> VertexOutput {
        let world_pos = uniforms.model_mat * vec4f(in.pos.xyz, 1.0f);
        let clip_pos = uniforms.view_proj_mat * world_pos;
        let color = uniforms.color;
        let uv = in.uv;
        return VertexOutput(clip_pos, color, uv);
    }
    @fragment
    fn fs_main(in: VertexOutput) -> @location(0) vec4f {
        let texcolor = textureSample(tex, samp, in.uv);
        <OUTCOLOR>
        return vec4(in.color.rgb * outcolor, 1.0);
    }
    """.replace("<OUTCOLOR>", outcolor)


class Bindgroup:
    def __init__(self, device: xg.Device, itemsize: int):
        builder = BinderBuilder(device)
        self.uniforms = builder.add_buffer(
            binding=0,
            visibility=xg.ShaderStage.Vertex | xg.ShaderStage.Fragment,
            type=xg.BufferBindingType.Uniform,
        )
        self.tex = builder.add_texture(
            binding=1,
            visibility=xg.ShaderStage.Fragment,
            sampletype=xg.TextureSampleType.Float,
            viewdim=xg.TextureViewDimension._2D,
        )
        self.samp = builder.add_sampler(binding=2, visibility=xg.ShaderStage.Fragment)
        self.sampler = device.createSampler(
            minFilter=xg.FilterMode.Linear,
            magFilter=xg.FilterMode.Linear,
            mipmapFilter=xg.MipmapFilterMode.Linear,
            compare=xg.CompareFunction.Undefined,
        )
        self.binder = builder.complete()
        self.layout = self.binder.layout
        self.itemsize = itemsize

    def bind(self, buffer: xg.Buffer, idx: int, tex: xg.TextureView) -> xg.BindGroup:
        self.uniforms.set(buffer, offset=idx * self.itemsize, size=self.itemsize)
        self.tex.set(tex)
        self.samp.set(self.sampler)
        return self.binder.create_bindgroup()


def create_geometry_buffers(device: XDevice) -> Tuple[xg.Buffer, xg.Buffer]:
    raw_verts = []
    raw_indices = []
    i0 = 0
    for axis in range(3):
        for z in [-1.0, 1.0]:
            for u in [-1.0, 1.0]:
                for v in [-1.0, 1.0]:
                    vert = np.roll([u, v, z], axis)
                    texu = u * 0.5 + 0.5
                    texv = v * 0.5 + 0.5
                    raw_verts.extend([vert[0], vert[1], vert[2], 1.0, texu, texv])
            if z > 0:
                raw_indices.extend([i0, i0 + 1, i0 + 3, i0 + 3, i0 + 2, i0])
            else:
                raw_indices.extend([i0, i0 + 3, i0 + 1, i0 + 3, i0, i0 + 2])
            i0 += 4

    vdata = bytes(np.array(raw_verts, dtype=np.float32))
    idata = bytes(np.array(raw_indices, dtype=np.uint16))

    vbuff = device.createBufferWithData(vdata, xg.BufferUsage.Vertex)
    ibuff = device.createBufferWithData(idata, xg.BufferUsage.Index)
    return vbuff, ibuff


def main() -> None:
    WIDTH = 768
    HEIGHT = 768

    window = GLFWWindow(WIDTH, HEIGHT, "woo")

    # Enable shader debug if you want to have wgsl source available (e.g., in RenderDoc)
    _, adapter, device, surface = xg.extensions.startup(
        surface_src=window.get_surface, debug=False
    )
    assert surface is not None, "Failed to get surface!"

    texdatas: List[TextureData] = [
        open_ktx("assets/stone_window_256.ktx2"),
        open_image("assets/stone_window.jpg"),
    ]

    textures = [
        data.create_texture(device, xg.TextureUsage.TextureBinding) for data in texdatas
    ]
    texviews = [
        tex.createView(
            format=xg.TextureFormat.Undefined,
            dimension=xg.TextureViewDimension.Undefined,
            mipLevelCount=tex.getMipLevelCount(),
            arrayLayerCount=1,
        )
        for tex in textures
    ]

    uniform_align = device.getLimits2().minUniformBufferOffsetAlignment
    print("Alignment requirement:", uniform_align)
    UNIFORMS_DTYPE = np.dtype(
        {
            "names": ["viewproj_mat", "model_mat", "color"],
            "formats": [
                np.dtype((np.float32, (4, 4))),
                np.dtype((np.float32, (4, 4))),
                np.dtype((np.float32, 4)),
            ],
            "offsets": [0, 64, 128],
            "itemsize": max(uniform_align, 256),
        }
    )

    bind_factory = Bindgroup(device, UNIFORMS_DTYPE.itemsize)
    pipeline_layout = device.createPipelineLayout(bindGroupLayouts=[bind_factory.layout])

    window_tex_format = get_preferred_format(adapter, surface)
    print("Window tex format:", window_tex_format.name)

    window.configure_surface(device, window_tex_format)

    shader_src = get_source("srgb" in window_tex_format.name.lower())
    shader = device.createWGSLShaderModule(code=shader_src, label="colorcube.wgsl")

    REPLACE = xg.blendComponent(
        srcFactor=xg.BlendFactor.One,
        dstFactor=xg.BlendFactor.Zero,
        operation=xg.BlendOperation.Add,
    )
    primitive = xg.primitiveState(
        topology=xg.PrimitiveTopology.TriangleList,
        stripIndexFormat=xg.IndexFormat.Undefined,
        frontFace=xg.FrontFace.CW,
        cullMode=xg.CullMode.Back,
    )
    color_target = xg.colorTargetState(
        format=window_tex_format,
        blend=xg.blendState(color=REPLACE, alpha=REPLACE),
        writeMask=xg.ColorWriteMask.All,
    )

    vertex_layout = auto_vertex_layout(
        [
            xg.VertexFormat.Float32x4,  # Position
            xg.VertexFormat.Float32x2,  # UV
        ]
    )

    render_pipeline = device.createRenderPipeline(
        layout=pipeline_layout,
        vertex=xg.vertexState(
            module=shader,
            entryPoint="vs_main",
            constants=[],
            buffers=[vertex_layout],
        ),
        primitive=primitive,
        multisample=xg.multisampleState(),
        fragment=xg.fragmentState(
            module=shader,
            entryPoint="fs_main",
            constants=[],
            targets=[color_target],
        ),
    )
    assert render_pipeline.isValid(), "Failed to create pipeline!"

    vbuff, ibuff = create_geometry_buffers(device)

    CUBECOUNT = len(texviews)

    draw_ubuff = device.createBuffer(
        usage=xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=UNIFORMS_DTYPE.itemsize * CUBECOUNT,
    )
    cpu_draw_ubuff = np.zeros(CUBECOUNT, dtype=UNIFORMS_DTYPE)
    draw_ubuff_staging = xg.DataPtr.wrap(cpu_draw_ubuff)

    projmat = proj_perspective(np.pi / 3.0, 1.0, 0.1, 20.0).T
    for idx in range(CUBECOUNT):
        cpu_draw_ubuff[idx]["viewproj_mat"] = projmat
        cpu_draw_ubuff[idx]["color"] = (1.0, 1.0, 1.0, 1.0)

    frame = 0

    # we can save a bit of time by premaking all bindgroups
    bgs = [
        bind_factory.bind(draw_ubuff, idx, texview)
        for idx, texview in enumerate(texviews)
    ]

    while window.poll():
        for uidx, xpos in enumerate(np.linspace(-1.0, 1.0, CUBECOUNT)):
            pos = np.array(
                [xpos, 0.0, math.sin(frame / 120.0) * 5.0 - 7.0], dtype=np.float32
            )
            set_transform(
                cpu_draw_ubuff[uidx]["model_mat"],
                (
                    math.sin(frame * 0.03) * 0.5,
                    math.sin(frame * 0.04) * 0.5,
                    frame * 0.02,
                ),
                0.9 / CUBECOUNT,
                pos,
            )

        command_encoder = device.createCommandEncoder()
        queue = device.getQueue()
        queue.writeBuffer(draw_ubuff, 0, draw_ubuff_staging)

        color_view = window.begin_frame()

        color_attachment = xg.renderPassColorAttachment(
            view=color_view,
            depthSlice=0,
            loadOp=xg.LoadOp.Clear,
            storeOp=xg.StoreOp.Store,
            clearValue=xg.color(r=0.5, g=0.5, b=0.5, a=1.0),
        )
        render_pass = command_encoder.beginRenderPass(colorAttachments=[color_attachment])

        render_pass.setPipeline(render_pipeline)
        render_pass.setVertexBuffer(0, vbuff, 0, vbuff.getSize())
        render_pass.setIndexBuffer(ibuff, xg.IndexFormat.Uint16, 0, ibuff.getSize())

        for bg in bgs:
            render_pass.setBindGroup(0, bg, [])
            render_pass.drawIndexed(36, 1, 0, 0, 0)

        render_pass.end()

        queue.submit([command_encoder.finish()])

        window.end_frame(present=True)

        command_encoder.release()
        render_pass.release()

        frame += 1
    print("Window close requested.")


if __name__ == "__main__":
    main()
