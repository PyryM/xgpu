"""
Stress test doing a lot of draw calls the naive way (without instancing)
"""

import time

import glfw_window
import numpy as np
import trimesh
from example_utils import buffer_layout_entry, proj_perspective
from numpy.typing import NDArray

import xgpu as xg
from xgpu.conveniences import create_buffer_with_data, get_adapter, get_device


def set_transform(target: NDArray, rot, scale: float, pos: NDArray):
    # Note: webgpu expects column-major array order
    r = trimesh.transformations.euler_matrix(rot[0], rot[1], rot[2])
    target[0:3, 0:3] = r[0:3, 0:3].T * scale
    target[3, 0:3] = pos
    target[3, 3] = 1.0


SHADER_SOURCE = """
struct GlobalUniforms {
  @align(16) view_proj_mat: mat4x4<f32>
}
struct DrawUniforms {
  @align(16) model_mat: mat4x4<f32>,
  @align(16) color: vec4<f32>,
}
@group(0) @binding(0) var<uniform> global_uniforms: GlobalUniforms;
@group(1) @binding(0) var<uniform> draw_uniforms: DrawUniforms;
struct VertexInput {
    @location(0) pos: vec4<f32>,
};
struct VertexOutput {
    @builtin(position) pos: vec4<f32>,
    @location(0) color : vec4<f32>,
};
@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    let world_pos = draw_uniforms.model_mat * vec4<f32>(in.pos.xyz, 1.0f);
    let clip_pos = global_uniforms.view_proj_mat * world_pos;
    let color = draw_uniforms.color * clamp(in.pos, vec4<f32>(0.0f), vec4<f32>(1.0f));
    return VertexOutput(clip_pos, color);
}
@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    return in.color;
}
"""

GLOBALUNIFORMS_DTYPE = np.dtype(
    {
        "names": ["view_proj_mat"],
        "formats": [np.dtype((np.float32, (4, 4)))],
        "offsets": [0],
        "itemsize": 64,
    }
)


def create_geometry_buffers(device: xg.Device):
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

    vbuff = create_buffer_with_data(device, vdata, xg.BufferUsage.Vertex)
    ibuff = create_buffer_with_data(device, idata, xg.BufferUsage.Index)
    return vbuff, ibuff


def main():
    WIDTH = 1024
    HEIGHT = 1024

    window = glfw_window.GLFWWindow(WIDTH, HEIGHT, "woo")

    instance = xg.createInstance()
    surface = window.get_surface(instance)
    (adapter, _) = get_adapter(instance, xg.PowerPreference.HighPerformance, surface)
    device = get_device(adapter)

    limits = xg.SupportedLimits()
    device.getLimits(limits)
    uniform_align = limits.limits.minUniformBufferOffsetAlignment
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
    bind_layout = device.createBindGroupLayout(
        entries=[
            buffer_layout_entry(
                binding=0,
                visibility=xg.ShaderStage.Vertex | xg.ShaderStage.Fragment,
                bind_type=xg.BufferBindingType.Uniform,
            ),
        ]
    )
    pipeline_layout = device.createPipelineLayout(
        bindGroupLayouts=[bind_layout, bind_layout]
    )

    window_tex_format = xg.TextureFormat.BGRA8Unorm
    # surface.getPreferredFormat(adapter)
    print("Window tex format:", window_tex_format.name)

    window.configure_surface(device, window_tex_format)

    shader = device.createShaderModule(
        nextInChain=xg.ChainedStruct([xg.shaderModuleWGSLDescriptor(code=SHADER_SOURCE)]),
        hints=[],
    )

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
    render_pipeline.assert_valid()

    surf_tex = xg.SurfaceTexture()

    ROWS = 30
    COLS = 30
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

    perf_times = []
    frame = 0
    while window.poll():
        # Update model matrices: this is surprisingly expensive in Python,
        # so we don't include this time in the performance measurements
        uidx = 0
        pos = np.array([0.0, 0.0, -2.0], dtype=np.float32)
        for y in np.linspace(-1.0, 1.0, ROWS):
            for x in np.linspace(-1.0, 1.0, COLS):
                pos[0] = x
                pos[1] = y
                set_transform(
                    cpu_draw_ubuff[uidx]["model_mat"],
                    [frame * 0.02 + x + y, frame * 0.03 + x, frame * 0.04 + y],
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

        surface.getCurrentTexture(surf_tex)

        color_view = surf_tex.texture.createView(
            format=xg.TextureFormat.Undefined,
            dimension=xg.TextureViewDimension._2D,
            mipLevelCount=1,
            arrayLayerCount=1,
        )

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

        global_bg = device.createBindGroup(
            layout=bind_layout,
            entries=[
                xg.bindGroupEntry(
                    binding=0,
                    buffer=global_ubuff,
                    offset=0,
                    size=global_ubuff.getSize(),
                ),
            ],
        )
        render_pass.setBindGroup(0, global_bg, [])

        bgs = []
        for drawidx in range(ROWS * COLS):
            bgs.append(
                device.createBindGroup(
                    layout=bind_layout,
                    entries=[
                        xg.bindGroupEntry(
                            binding=0,
                            buffer=draw_ubuff,
                            offset=drawidx * DRAWUNIFORMS_DTYPE.itemsize,
                            size=DRAWUNIFORMS_DTYPE.itemsize,
                        ),
                    ],
                )
            )

        for bg in bgs:
            render_pass.setBindGroup(1, bg, [])
            render_pass.drawIndexed(12 * 3, 1, 0, 0, 0)
        render_pass.end()

        queue.submit([command_encoder.finish()])

        for bg in bgs:
            bg.release()

        # We end timing here because if we time surface.present()
        # we'll just measure vsync timing
        dt = time.perf_counter_ns() - t0
        surface.present()

        color_view.release()
        command_encoder.release()
        render_pass.release()
        surf_tex.texture.release()

        perf_times.append(dt / 1e6)  # convert to ms
        if frame < 1000 and frame % 100 == 0:
            print(frame)
        elif frame == 1000:
            # write performance info
            print("Mean time per frame:", np.mean(perf_times))
            with open("timings_xgpu.txt", "w") as dest:
                dest.write("\n".join([str(t) for t in perf_times]))
        frame += 1
    print("Window close requested.")


if __name__ == "__main__":
    main()
