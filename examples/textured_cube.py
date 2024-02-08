"""
Textured cube
"""

from typing import List, Tuple

import numpy as np
import trimesh
from example_utils import proj_perspective
from numpy.typing import NDArray

import xgpu as xg
from xgpu.extensions import BinderBuilder, XDevice, auto_vertex_layout
from xgpu.extensions.glfw_window import GLFWWindow
from xgpu.extensions.ktx import KTXTextureData

def set_transform(
    target: NDArray, rot: Tuple[float, float, float], scale: float, pos: NDArray
) -> None:
    # Note: webgpu expects column-major array order
    r = trimesh.transformations.euler_matrix(rot[0], rot[1], rot[2])
    target[0:3, 0:3] = r[0:3, 0:3].T * scale
    target[3, 0:3] = pos
    target[3, 3] = 1.0


SHADER_SOURCE = """
struct Uniforms {
  @align(16) view_proj_mat: mat4x4f
  @align(16) model_mat: mat4x4f,
  @align(16) color: vec4f,
}
@group(0) @binding(0) var<uniform> uniforms: GlobalUniforms;
@group(0) @binding(1) var tex: texture_2d<f32>;
@group(0) @binding(2) var samp: sampler;

struct VertexInput {
    @location(0) pos: vec4f,
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
    let color = uniforms.color * clamp(in.pos, vec4f(0.0f), vec4f(1.0f));
    let uv = (in.pos.xy + vec2f(1.0)) * 0.5;
    return VertexOutput(clip_pos, color, uv);
}
@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let texcolor = textureSample(tex, samp, in.uv);
    return in.color * texcolor;
}
"""

class Bindgroup:
    def __init__(self, device: xg.Device):
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
            viewdim=xg.TextureViewDimension._2D
        )
        self.samp = builder.add_sampler(binding=2, visibility=xg.ShaderStage.Fragment)
        self.sampler = device.createSampler(
            minFilter=xg.FilterMode.Linear,
            magFilter=xg.FilterMode.Linear,
            mipmapFilter=xg.MipmapFilterMode.Linear,
            compare=xg.CompareFunction.Undefined
        )
        self.binder = builder.complete()
        self.layout = self.binder.layout

    def bind(
        self, buffer: xg.Buffer, tex: xg.TextureView
    ) -> xg.BindGroup:
        self.uniforms.set(buffer)
        self.tex.set(tex)
        self.samp.set(self.sampler)
        return self.binder.create_bindgroup()


def create_geometry_buffers(device: XDevice) -> Tuple[xg.Buffer, xg.Buffer]:
    raw_verts = []
    for z in [-1.0, 1.0]:
        for y in [-1.0, 1.0]:
            for x in [-1.0, 1.0]:
                raw_verts.extend([x, y, z, 1.0])

    vdata = bytes(np.array(raw_verts, dtype=np.float32))
    indexlist = """
    0 1 3 3 2 0
    1 5 7 7 3 1
    4 6 7 7 5 4
    2 6 4 4 0 2
    0 4 5 5 1 0
    3 7 6 6 2 3
    """
    raw_indices = [int(s) for s in indexlist.split()]
    idata = bytes(np.array(raw_indices, dtype=np.uint16))

    vbuff = device.createBufferWithData(vdata, xg.BufferUsage.Vertex)
    ibuff = device.createBufferWithData(idata, xg.BufferUsage.Index)
    return vbuff, ibuff


def main() -> None:
    WIDTH = 1024
    HEIGHT = 1024

    window = GLFWWindow(WIDTH, HEIGHT, "woo")

    # Enable shader debug if you want to have wgsl source available (e.g., in RenderDoc)
    _, adapter, device, surface = xg.extensions.startup(
        surface_src=window.get_surface, debug=False
    )
    assert surface is not None, "Failed to get surface!"

    with open("assets/test.ktx", "rb") as src:
        texdata = KTXTextureData(src.read())
        the_tex = texdata.create_texture(
            device,
            xg.TextureUsage.TextureBinding
        )
    the_tex_view = the_tex.createView(
        format=xg.TextureFormat.Undefined,
        dimension=xg.TextureViewDimension.Undefined,
        mipLevelCount=the_tex.getMipLevelCount(),
        arrayLayerCount=1
    )

    uniform_align = device.getLimits2().minUniformBufferOffsetAlignment
    print("Alignment requirement:", uniform_align)
    UNIFORMS_DTYPE = np.dtype(
        {
            "names": ["viewproj_mat", "model_mat", "color"],
            "formats": [np.dtype((np.float32, (4, 4))), np.dtype((np.float32, (4, 4))), np.dtype((np.float32, 4))],
            "offsets": [0, 64],
            "itemsize": max(uniform_align, 128),
        }
    )

    bind_factory = Bindgroup(device)
    pipeline_layout = device.createPipelineLayout(
        bindGroupLayouts=[bind_factory.layout]
    )

    window_tex_format = surface.getPreferredFormat(adapter)
    # xg.TextureFormat.BGRA8Unorm
    print("Window tex format:", window_tex_format.name)

    window.configure_surface(device, window_tex_format)

    shader = device.createWGSLShaderModule(code=SHADER_SOURCE, label="colorcube.wgsl")

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
            xg.VertexFormat.Float32x4  # Position
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

    draw_ubuff = device.createBuffer(
        usage=xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=UNIFORMS_DTYPE.itemsize,
    )
    cpu_draw_ubuff = np.zeros((), dtype=UNIFORMS_DTYPE)
    draw_ubuff_staging = xg.DataPtr.wrap(cpu_draw_ubuff)

    cpu_draw_ubuff["view_proj_mat"] = proj_perspective(np.pi / 3.0, 1.0, 0.1, 10.0).T

    frame = 0

    while window.poll():
        # Update model matrices: this is surprisingly expensive in Python,
        # so we don't include this time in the performance measurements
        uidx = 0
        pos = np.array([0.0, 0.0, -2.0], dtype=np.float32)
        set_transform(
            cpu_draw_ubuff["model_mat"],
            (frame * 0.02, frame * 0.03, frame * 0.04),
            0.7,
            pos,
        )
        cpu_draw_ubuff["color"] = (1.0, 1.0, 1.0, 1.0)
        uidx += 1

        command_encoder = device.createCommandEncoder()
        queue = device.getQueue()
        queue.writeBuffer(draw_ubuff, 0, draw_ubuff_staging)

        color_view = window.begin_frame()

        color_attachment = xg.renderPassColorAttachment(
            view=color_view,
            loadOp=xg.LoadOp.Clear,
            storeOp=xg.StoreOp.Store,
            clearValue=xg.color(r=0.5, g=0.5, b=0.5, a=1.0),
        )
        render_pass = command_encoder.beginRenderPass(colorAttachments=[color_attachment])

        render_pass.setPipeline(render_pipeline)
        render_pass.setVertexBuffer(0, vbuff, 0, vbuff.getSize())
        render_pass.setIndexBuffer(ibuff, xg.IndexFormat.Uint16, 0, ibuff.getSize())

        bg = bind_factory.bind(draw_ubuff, the_tex_view)
        render_pass.setBindGroup(0, bg, [])
        render_pass.drawIndexed(12 * 3, 1, 0, 0, 0)
        render_pass.end()

        queue.submit([command_encoder.finish()])

        bg.release()

        window.end_frame(present=True)

        command_encoder.release()
        render_pass.release()

        frame += 1
    print("Window close requested.")


if __name__ == "__main__":
    main()
