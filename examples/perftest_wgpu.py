"""
Stress test doing a lot of draw calls the naive way (without instancing)
"""

import time

import numpy as np
import trimesh
import wgpu
from example_utils import proj_perspective
from numpy.typing import NDArray


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


def create_geometry_buffers(device: wgpu.GPUDevice):
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

    vbuff = device.create_buffer_with_data(data=vdata, usage=wgpu.BufferUsage.VERTEX)
    ibuff = device.create_buffer_with_data(data=idata, usage=wgpu.BufferUsage.INDEX)
    return vbuff, ibuff


def main(canvas):
    adapter = wgpu.gpu.request_adapter(power_preference="high-performance")
    device = adapter.request_device(required_limits=adapter.limits)

    present_context = canvas.get_context()
    window_tex_format = present_context.get_preferred_format(device.adapter)
    present_context.configure(device=device, format=window_tex_format)

    uniform_align = device.limits["min_uniform_buffer_offset_alignment"]
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
    bind_layout = device.create_bind_group_layout(
        entries=[
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.VERTEX | wgpu.ShaderStage.FRAGMENT,
                "buffer": {
                    "type": wgpu.BufferBindingType.uniform,
                    "has_dynamic_offset": False,
                    "min_binding_size": 0,
                },
            },
        ]
    )
    pipeline_layout = device.create_pipeline_layout(
        bind_group_layouts=[bind_layout, bind_layout]
    )

    shader = device.create_shader_module(code=SHADER_SOURCE)

    REPLACE = {
        "src_factor": wgpu.BlendFactor.one,
        "dst_factor": wgpu.BlendFactor.zero,
        "operation": wgpu.BlendOperation.add,
    }
    primitive = {
        "topology": wgpu.PrimitiveTopology.triangle_list,
        "front_face": wgpu.FrontFace.cw,
        "cull_mode": wgpu.CullMode.back,
    }
    color_target = {
        "format": window_tex_format,
        "blend": {"color": REPLACE, "alpha": REPLACE},
        "write_mask": wgpu.ColorWrite.ALL,
    }

    render_pipeline = device.create_render_pipeline(
        layout=pipeline_layout,
        vertex={
            "module": shader,
            "entry_point": "vs_main",
            "buffers": [
                {
                    "array_stride": 16,
                    "step_mode": wgpu.VertexStepMode.vertex,
                    "attributes": [
                        {
                            "format": wgpu.VertexFormat.float32x4,
                            "offset": 0,
                            "shader_location": 0,
                        },
                    ],
                },
            ],
        },
        primitive=primitive,
        multisample=None,
        fragment={
            "module": shader,
            "entry_point": "fs_main",
            "targets": [color_target],
        },
    )

    ROWS = 30
    COLS = 30
    PRIM_COUNT = ROWS * COLS

    vbuff, ibuff = create_geometry_buffers(device)

    global_ubuff = device.create_buffer(
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        size=GLOBALUNIFORMS_DTYPE.itemsize,
    )
    cpu_global_ubuff = np.zeros((), dtype=GLOBALUNIFORMS_DTYPE)

    draw_ubuff = device.create_buffer(
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        size=DRAWUNIFORMS_DTYPE.itemsize * PRIM_COUNT,
    )
    cpu_draw_ubuff = np.zeros((PRIM_COUNT), dtype=DRAWUNIFORMS_DTYPE)

    cpu_global_ubuff["view_proj_mat"] = proj_perspective(np.pi / 3.0, 1.0, 0.1, 10.0).T

    gframe = [0]
    perf_times = []

    def draw_frame():
        frame = gframe[0]

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
        command_encoder = device.create_command_encoder()
        queue = device.queue
        queue.write_buffer(global_ubuff, 0, cpu_global_ubuff)
        queue.write_buffer(draw_ubuff, 0, cpu_draw_ubuff)

        current_texture = present_context.get_current_texture()
        color_view = current_texture.create_view()

        color_attachment = {
            "view": color_view,
            "load_op": wgpu.LoadOp.clear,
            "store_op": wgpu.StoreOp.store,
            "clear_value": (0.5, 0.5, 0.5, 1.0),
        }
        render_pass = command_encoder.begin_render_pass(
            color_attachments=[color_attachment]
        )

        render_pass.set_pipeline(render_pipeline)
        render_pass.set_vertex_buffer(0, vbuff, 0, vbuff.size)
        render_pass.set_index_buffer(ibuff, wgpu.IndexFormat.uint16, 0, ibuff.size)

        global_bg = device.create_bind_group(
            layout=bind_layout,
            entries=[
                {
                    "binding": 0,
                    "resource": {
                        "buffer": global_ubuff,
                        "offset": 0,
                        "size": global_ubuff.size,
                    },
                },
            ],
        )
        render_pass.set_bind_group(0, global_bg, [], 0, 0)

        bgs = []
        for drawidx in range(ROWS * COLS):
            bgs.append(
                device.create_bind_group(
                    layout=bind_layout,
                    entries=[
                        {
                            "binding": 0,
                            "resource": {
                                "buffer": draw_ubuff,
                                "offset": drawidx * DRAWUNIFORMS_DTYPE.itemsize,
                                "size": DRAWUNIFORMS_DTYPE.itemsize,
                            },
                        },
                    ],
                )
            )

        for bg in bgs:
            render_pass.set_bind_group(1, bg, [], 0, 0)
            render_pass.draw_indexed(12 * 3, 1, 0, 0, 0)
        render_pass.end()

        queue.submit([command_encoder.finish()])

        # We end timing here because if we time surface.present()
        # we'll just measure vsync timing
        dt = time.perf_counter_ns() - t0

        perf_times.append(dt / 1e6)  # convert to ms
        if frame < 1000 and frame % 100 == 0:
            print(frame)
        elif frame == 1000:
            # write performance info
            print("Mean time per frame:", np.mean(perf_times))
            with open("timings_wgpu.txt", "w") as dest:
                dest.write("\n".join([str(t) for t in perf_times]))
        gframe[0] += 1

        canvas.request_draw(draw_frame)

    canvas.request_draw(draw_frame)
    return device


if __name__ == "__main__":
    from wgpu.gui.auto import WgpuCanvas, run

    WIDTH = 1024
    HEIGHT = 1024
    canvas = WgpuCanvas(size=(WIDTH, HEIGHT))
    main(canvas)
    run()
