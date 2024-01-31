"""
Stress test doing a lot of draw calls the naive way (without instancing)
Version which uses the BinderBuilder utility which is somewhat faster
at creating bind groups than doing things the naive/explicit way.
"""

import time
from typing import List, Optional

import glfw_window
import numpy as np
import trimesh
from example_utils import proj_perspective
from numpy.typing import NDArray

import xgpu as xg
from xgpu.extensions import BinderBuilder, XDevice


def set_transform(target: NDArray, rot, scale: float, pos: NDArray):
    # Note: webgpu expects column-major array order
    r = trimesh.transformations.euler_matrix(rot[0], rot[1], rot[2])
    target[0:3, 0:3] = r[0:3, 0:3].T * scale
    target[3, 0:3] = pos
    target[3, 3] = 1.0


SHADER_SOURCE = """
struct GlobalUniforms {
  @align(16) view_proj_mat: mat4x4f
}
struct DrawUniforms {
  @align(16) model_mat: mat4x4f,
  @align(16) color: vec4f,
}
@group(0) @binding(0) var<uniform> global_uniforms: GlobalUniforms;
@group(1) @binding(0) var<uniform> draw_uniforms: DrawUniforms;
struct VertexInput {
    @location(0) pos: vec4f,
};
struct VertexOutput {
    @builtin(position) pos: vec4f,
    @location(0) color : vec4f,
};
@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    let world_pos = draw_uniforms.model_mat * vec4f(in.pos.xyz, 1.0f);
    let clip_pos = global_uniforms.view_proj_mat * world_pos;
    let color = draw_uniforms.color * clamp(in.pos, vec4f(0.0f), vec4f(1.0f));
    return VertexOutput(clip_pos, color);
}
@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    return in.color;
}
"""


class UniformsBindgroup:
    def __init__(self, device: xg.Device):
        builder = BinderBuilder(device)
        self.uniforms = builder.add_buffer(
            binding=0,
            visibility=xg.ShaderStage.Vertex | xg.ShaderStage.Fragment,
            type=xg.BufferBindingType.Uniform,
        )
        self.binder = builder.complete()
        self.layout = self.binder.layout

    def bind(
        self, buffer: xg.Buffer, offset: int = 0, size: Optional[int] = None
    ) -> xg.BindGroup:
        self.uniforms.set(buffer, offset, size)
        return self.binder.create_bindgroup()


GLOBALUNIFORMS_DTYPE = np.dtype(
    {
        "names": ["view_proj_mat"],
        "formats": [np.dtype((np.float32, (4, 4)))],
        "offsets": [0],
        "itemsize": 64,
    }
)


def create_geometry_buffers(device: XDevice):
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


def main():
    WIDTH = 1024
    HEIGHT = 1024

    window = glfw_window.GLFWWindow(WIDTH, HEIGHT, "woo")

    # Enable shader debug if you want to have wgsl source available (e.g., in RenderDoc)
    _, adapter, device, surface = xg.helpers.startup(
        surface_src=window.get_surface, debug=False
    )
    assert surface is not None, "Failed to get surface!"

    uniform_align = device.getLimits2().minUniformBufferOffsetAlignment
    print("Alignment requirement:", uniform_align)
    DRAWUNIFORMS_DTYPE = np.dtype(
        {
            "names": ["model_mat", "color"],
            "formats": [np.dtype((np.float32, (4, 4))), np.dtype((np.float32, 4))],
            "offsets": [0, 64],
            "itemsize": max(uniform_align, 128),
        }
    )

    # same layout for both global and draw uniforms
    bind_factory = UniformsBindgroup(device)
    pipeline_layout = device.createPipelineLayout(
        bindGroupLayouts=[bind_factory.layout, bind_factory.layout]
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

    render_pipeline = device.createRenderPipeline(
        layout=pipeline_layout,
        vertex=xg.vertexState(
            module=shader,
            entryPoint="vs_main",
            constants=[],
            buffers=[
                xg.vertexBufferLayout(
                    arrayStride=16,
                    stepMode=xg.VertexStepMode.Vertex,
                    attributes=[
                        xg.vertexAttribute(
                            format=xg.VertexFormat.Float32x4,
                            offset=0,
                            shaderLocation=0,
                        ),
                    ],
                ),
            ],
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

    ROWS = 32
    COLS = 32
    PRIM_COUNT = ROWS * COLS

    vbuff, ibuff = create_geometry_buffers(device)

    global_ubuff = device.createBuffer(
        usage=xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=GLOBALUNIFORMS_DTYPE.itemsize,
    )
    cpu_global_ubuff = np.zeros((), dtype=GLOBALUNIFORMS_DTYPE)
    global_ubuff_staging = xg.DataPtr.wrap(cpu_global_ubuff)

    draw_ubuff = device.createBuffer(
        usage=xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=DRAWUNIFORMS_DTYPE.itemsize * PRIM_COUNT,
    )
    cpu_draw_ubuff = np.zeros((PRIM_COUNT), dtype=DRAWUNIFORMS_DTYPE)
    draw_ubuff_staging = xg.DataPtr.wrap(cpu_draw_ubuff)

    cpu_global_ubuff["view_proj_mat"] = proj_perspective(np.pi / 3.0, 1.0, 0.1, 10.0).T

    frame = 0
    perf_times = []
    frame_times = []
    last_frame_t = time.perf_counter_ns()

    while window.poll():
        cur_ft = time.perf_counter_ns()
        frame_times.append((cur_ft - last_frame_t) / 1e6)
        last_frame_t = cur_ft

        # Update model matrices: this is surprisingly expensive in Python,
        # so we don't include this time in the performance measurements
        uidx = 0
        pos = np.array([0.0, 0.0, -2.0], dtype=np.float32)
        for y in np.linspace(-1.0, 1.0, ROWS):
            for x in np.linspace(-1.0, 1.0, COLS):
                pos[0] = x
                pos[1] = y
                r = 5.0 * ((x**2.0) + (y**2.0)) ** 0.5
                set_transform(
                    cpu_draw_ubuff[uidx]["model_mat"],
                    [frame * 0.02 + r, frame * 0.03 + r, frame * 0.04],
                    0.7 / ROWS,
                    pos,
                )
                cpu_draw_ubuff[uidx]["color"] = (1.0, 1.0, 1.0, 1.0)
                uidx += 1

        # Time this block of webgpu calls
        t0 = time.perf_counter_ns()
        command_encoder = device.createCommandEncoder()
        queue = device.getQueue()
        queue.writeBuffer(global_ubuff, 0, global_ubuff_staging)
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

        global_bg = bind_factory.bind(global_ubuff)
        render_pass.setBindGroup(0, global_bg, [])

        bgs: List[xg.BindGroup] = []
        doffset = DRAWUNIFORMS_DTYPE.itemsize
        isize = DRAWUNIFORMS_DTYPE.itemsize
        for idx in range(ROWS * COLS):
            bgs.append(bind_factory.bind(draw_ubuff, idx * doffset, isize))

        for bg in bgs:
            render_pass.setBindGroup(1, bg, [])
            render_pass.drawIndexed(12 * 3, 1, 0, 0, 0)
        render_pass.end()

        queue.submit([command_encoder.finish()])

        for bg in bgs:
            bg.release()

        # We end timing here because if we time window.end_frame()
        # we'll just measure vsync timing
        dt = time.perf_counter_ns() - t0
        window.end_frame(present=True)

        command_encoder.release()
        render_pass.release()

        perf_times.append(dt / 1e6)  # convert to ms
        if frame < 1000 and frame % 100 == 0:
            print(frame)
        elif frame == 1000:
            # write performance info
            print("Mean API time per frame:", np.mean(perf_times))
            print("Mean full time per frame:", np.mean(frame_times))
            with open("full_frame_timings_xgpu_bindbuilder.txt", "w") as dest:
                dest.write("\n".join([str(t) for t in frame_times]))
            with open("timings_xgpu_bindbuilder.txt", "w") as dest:
                dest.write("\n".join([str(t) for t in perf_times]))
        frame += 1
    print("Window close requested.")


if __name__ == "__main__":
    main()
