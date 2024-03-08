"""
Example of using material capture
"""

from typing import List, Optional, Tuple

import numpy as np
from example_utils import proj_perspective
from numpy.typing import NDArray
from trimesh_helpers import euler_matrix, load_mesh_simple

import xgpu as xg
from xgpu.extensions import (
    BinderBuilder,
    XDevice,
    create_default_view,
)
from xgpu.extensions.glfw_window import GLFWWindow
from xgpu.extensions.standardimage import open_image
from xgpu.extensions.texloader import TextureData


def set_transform(
    target_pos: NDArray,
    target_norm: NDArray,
    rot: Tuple[float, float, float],
    scale: float,
    pos: NDArray,
) -> None:
    r = euler_matrix(*rot) * scale

    # Matrix to transform normals is modelmatrix.inv.transpose
    # (differs from model matrix under non-uniform scaling)
    norm_r = np.linalg.inv(r).T
    # Note: webgpu expects column-major array order
    target_pos[0:3, 0:3] = r.T
    target_pos[3, 0:3] = pos
    target_pos[3, 3] = 1.0
    target_norm[0:3, 0:3] = norm_r.T


def get_source(is_srgb: bool) -> str:
    return """
    struct ViewUniforms {
        @align(16) view_mat: mat4x4f,
        @align(16) proj_mat: mat4x4f,
    }

    struct Uniforms {
        @align(16) model_mat: mat4x4f,
        @align(16) normal_mat: mat4x4f,
        @align(16) tex_params: vec4f,
    }

    @group(0) @binding(0) var<uniform> view_uniforms: ViewUniforms;

    @group(1) @binding(0) var<uniform> uniforms: Uniforms;
    @group(1) @binding(1) var matcap: texture_2d<f32>;
    @group(1) @binding(2) var diffuse: texture_2d<f32>;
    @group(1) @binding(3) var samp: sampler;

    struct VertexInput {
        @location(0) position: vec3f,
        @location(1) color: vec3f,
        @location(2) normal: vec3f,
        @location(3) texcoord: vec2f
    }

    struct VertexOutput {
        @builtin(position) position: vec4f,
        @location(0) view_pos: vec3f,
        @location(1) view_normal: vec3f,
        @location(2) color: vec3f,
        @location(3) texcoord: vec2f,
    }

    @vertex
    fn vs_main(input: VertexInput) -> VertexOutput {
        let world_pos = uniforms.model_mat * vec4f(input.position.xyz, 1.0f);
        let world_normal = uniforms.normal_mat * vec4f(input.normal.xyz, 0.0f);
        let view_normal = view_uniforms.view_mat * world_normal;
        let view_pos = view_uniforms.view_mat * world_pos;
        let outpos = view_uniforms.proj_mat * view_pos;
        return VertexOutput(outpos, view_pos.xyz, view_normal.xyz, input.color.rgb, input.texcoord.xy);
    }

    @fragment
    fn fs_main(input: VertexOutput) -> @location(0) vec4f {
        let tex_params = uniforms.tex_params;
        var normal: vec3f = vec3f(0.0);
        if tex_params.z > 0.0 {
            // faceted: compute normal from screen-space derivatives
            normal = normalize(cross(dpdx(input.view_pos), dpdy(input.view_pos)));
        } else {
            // smooth shaded
            normal = normalize(input.view_normal);
        }
        let ns = normal.xy * 0.99;
        var samppos: vec2f = (ns + vec2f(1.0)) * 0.5;
        samppos.y = 1.0 - samppos.y;
        var outcolor: vec3f = textureSample(matcap, samp, samppos).rgb;
        if tex_params.x > 0.0 {
            let diffusecolor = textureSample(diffuse, samp, input.texcoord).rgb;
            outcolor *= diffusecolor;
        }
        if tex_params.y > 0.0 {
            outcolor *= input.color.rgb;
        }

        return vec4f(pow(outcolor.rgb, vec3f(2.2)), 1.0);
    }
    """


class ViewBindgroup:
    def __init__(self, device: XDevice):
        builder = BinderBuilder(device)
        self.uniforms = builder.add_buffer(
            binding=0,
            visibility=xg.ShaderStage.Vertex | xg.ShaderStage.Fragment,
            type=xg.BufferBindingType.Uniform,
        )
        self.binder = builder.complete()
        self.layout = self.binder.layout

    def bind(self, uniforms: xg.Buffer) -> xg.BindGroup:
        self.uniforms.set(uniforms)
        return self.binder.create_bindgroup()


class ModelBindgroup:
    def __init__(self, device: XDevice, itemsize: int):
        builder = BinderBuilder(device)
        self.uniforms = builder.add_buffer(
            binding=0,
            visibility=xg.ShaderStage.Vertex | xg.ShaderStage.Fragment,
            type=xg.BufferBindingType.Uniform,
        )
        self.matcap_tex = builder.add_texture(
            binding=1,
            visibility=xg.ShaderStage.Fragment,
            sampletype=xg.TextureSampleType.Float,
            viewdim=xg.TextureViewDimension._2D,
        )
        self.diffuse_tex = builder.add_texture(
            binding=2,
            visibility=xg.ShaderStage.Fragment,
            sampletype=xg.TextureSampleType.Float,
            viewdim=xg.TextureViewDimension._2D,
        )
        self.samp = builder.add_sampler(binding=3, visibility=xg.ShaderStage.Fragment)
        self.sampler = device.createSampler(
            minFilter=xg.FilterMode.Linear,
            magFilter=xg.FilterMode.Linear,
            mipmapFilter=xg.MipmapFilterMode.Linear,
            compare=xg.CompareFunction.Undefined,
        )
        self.binder = builder.complete()
        self.layout = self.binder.layout
        self.itemsize = itemsize

    def bind(
        self,
        uniforms: xg.Buffer,
        idx: int,
        matcaptex: xg.TextureView,
        diffusetex: Optional[xg.TextureView] = None,
    ) -> xg.BindGroup:
        self.uniforms.set(uniforms, offset=idx * self.itemsize, size=self.itemsize)
        self.matcap_tex.set(matcaptex)
        if diffusetex is not None:
            self.diffuse_tex.set(diffusetex)
        else:
            self.diffuse_tex.set(matcaptex)
        self.samp.set(self.sampler)

        return self.binder.create_bindgroup()


def load_geometry_buffers(
    device: XDevice, fn: str
) -> Tuple[xg.VertexBufferLayout, xg.Buffer, xg.Buffer, int, int]:
    raw_verts, raw_indices, vlayout = load_mesh_simple(fn)

    vdata = bytes(raw_verts)
    idata = bytes(raw_indices)
    vcount = len(raw_verts)
    icount = len(raw_indices)

    vbuff = device.createBufferWithData(vdata, xg.BufferUsage.Vertex)
    ibuff = device.createBufferWithData(idata, xg.BufferUsage.Index)
    return vlayout, vbuff, ibuff, vcount, icount


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
        open_image("assets/matcap_metal.jpg"),
        open_image("assets/stone_window.jpg"),
    ]

    textures = [
        data.create_texture(device, xg.TextureUsage.TextureBinding) for data in texdatas
    ]
    texviews = [create_default_view(tex) for tex in textures]

    uniform_align = device.getLimits2().minUniformBufferOffsetAlignment
    print("Alignment requirement:", uniform_align)
    MODEL_UNIFORMS_DTYPE = np.dtype(
        {
            "names": ["model_mat", "normal_mat", "tex_params"],
            "formats": [
                np.dtype((np.float32, (4, 4))),
                np.dtype((np.float32, (4, 4))),
                np.dtype((np.float32, 4)),
            ],
            "offsets": [0, 64, 128],
            "itemsize": 256,
        }
    )
    VIEW_UNIFORMS_DTYPE = np.dtype(
        {
            "names": ["view_mat", "proj_mat"],
            "formats": [
                np.dtype((np.float32, (4, 4))),
                np.dtype((np.float32, (4, 4))),
            ],
            "offsets": [0, 64],
            "itemsize": 256,
        }
    )

    model_bind_factory = ModelBindgroup(device, MODEL_UNIFORMS_DTYPE.itemsize)
    view_bind_factory = ViewBindgroup(device)
    pipeline_layout = device.createPipelineLayout(
        bindGroupLayouts=[view_bind_factory.layout, model_bind_factory.layout]
    )

    window_tex_format = surface.getPreferredFormat(adapter)
    print("Window tex format:", window_tex_format.name)

    window.configure_surface(device, window_tex_format)
    depth_tex = window.get_depth_buffer()
    depth_view = create_default_view(depth_tex)

    shader_src = get_source("srgb" in window_tex_format.name.lower())
    shader = device.createWGSLShaderModule(code=shader_src, label="matcap.wgsl")

    REPLACE = xg.blendComponent(
        srcFactor=xg.BlendFactor.One,
        dstFactor=xg.BlendFactor.Zero,
        operation=xg.BlendOperation.Add,
    )
    primitive = xg.primitiveState(
        topology=xg.PrimitiveTopology.TriangleList,
        stripIndexFormat=xg.IndexFormat.Undefined,
        frontFace=xg.FrontFace.CCW,
        cullMode=xg.CullMode.Back,
    )
    color_target = xg.colorTargetState(
        format=window_tex_format,
        blend=xg.blendState(color=REPLACE, alpha=REPLACE),
        writeMask=xg.ColorWriteMask.All,
    )

    vertex_layout, vbuff, ibuff, vcount, icount = load_geometry_buffers(device, "assets/cat.obj")

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
        depthStencil=xg.depthStencilState(
            format=depth_tex.getFormat(),
            depthWriteEnabled=True,
            depthCompare=xg.CompareFunction.Less,
            stencilFront=xg.stencilFaceState(),
            stencilBack=xg.stencilFaceState(),
        ),
    )
    assert render_pipeline.isValid(), "Failed to create pipeline!"

    CUBECOUNT = 2

    view_ubuff = device.createBuffer(
        usage=xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=VIEW_UNIFORMS_DTYPE.itemsize,
    )
    cpu_view_ubuff = np.zeros((), dtype=VIEW_UNIFORMS_DTYPE)
    view_ubuff_staging = xg.DataPtr.wrap(cpu_view_ubuff)

    model_ubuff = device.createBuffer(
        usage=xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=MODEL_UNIFORMS_DTYPE.itemsize * CUBECOUNT,
    )
    cpu_model_ubuff = np.zeros(CUBECOUNT, dtype=MODEL_UNIFORMS_DTYPE)
    model_ubuff_staging = xg.DataPtr.wrap(cpu_model_ubuff)

    projmat = proj_perspective(np.pi / 3.0, 1.0, 0.1, 20.0)
    viewmat = np.eye(4, dtype=np.float32)
    cpu_view_ubuff["view_mat"] = viewmat.T
    cpu_view_ubuff["proj_mat"] = projmat.T

    for idx in range(CUBECOUNT):
        cpu_model_ubuff[idx]["tex_params"] = (0.0, 0.0, idx % 2, 0.0)

    frame = 0

    # we can save a bit of time by premaking all bindgroups
    global_bg = view_bind_factory.bind(view_ubuff)
    bgs = [
        model_bind_factory.bind(model_ubuff, idx, texviews[0], texviews[1])
        for idx in range(CUBECOUNT)
    ]

    while window.poll():
        for uidx, xpos in enumerate(np.linspace(-0.5, 0.5, CUBECOUNT, endpoint=True)):
            pos = np.array([xpos, 0.0, -2.0], dtype=np.float32)
            rotspeed = -0.02 * ((uidx % 2) * 2.0 - 1.0)
            set_transform(
                cpu_model_ubuff[uidx]["model_mat"],
                cpu_model_ubuff[uidx]["normal_mat"],
                (0.0, frame * rotspeed, 0.0),
                1.0,
                pos,
            )

        command_encoder = device.createCommandEncoder()
        queue = device.getQueue()
        queue.writeBuffer(view_ubuff, 0, view_ubuff_staging)
        queue.writeBuffer(model_ubuff, 0, model_ubuff_staging)

        color_view = window.begin_frame()

        color_attachment = xg.renderPassColorAttachment(
            view=color_view,
            loadOp=xg.LoadOp.Clear,
            storeOp=xg.StoreOp.Store,
            clearValue=xg.color(r=0.5, g=0.5, b=0.5, a=1.0),
        )
        depth_attachment = xg.renderPassDepthStencilAttachment(
            view=depth_view,
            depthLoadOp=xg.LoadOp.Clear,
            depthStoreOp=xg.StoreOp.Store,
            depthClearValue=1.0,
            stencilLoadOp=xg.LoadOp.Undefined,
            stencilStoreOp=xg.StoreOp.Undefined,
        )
        render_pass = command_encoder.beginRenderPass(
            colorAttachments=[color_attachment], depthStencilAttachment=depth_attachment
        )

        render_pass.setPipeline(render_pipeline)
        render_pass.setVertexBuffer(0, vbuff, 0, vbuff.getSize())
        render_pass.setIndexBuffer(ibuff, xg.IndexFormat.Uint32, 0, ibuff.getSize())
        render_pass.setBindGroup(0, global_bg, [])

        for bg in bgs:
            render_pass.setBindGroup(1, bg, [])
            render_pass.drawIndexed(icount, 1, 0, 0, 0)

        render_pass.end()

        queue.submit([command_encoder.finish()])

        window.end_frame(present=True)

        command_encoder.release()
        render_pass.release()

        frame += 1
    print("Window close requested.")


if __name__ == "__main__":
    main()
