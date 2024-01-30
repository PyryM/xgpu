import os
from typing import Optional

import harness
import numpy as np
import trimesh
from numpy.typing import NDArray

import xgpu as xg
from xgpu.extensions import BinderBuilder


def set_transform(target: NDArray, rot, scale: float, pos: NDArray):
    # Note: webgpu expects column-major array order
    r = trimesh.transformations.euler_matrix(rot[0], rot[1], rot[2])
    target[0:3, 0:3] = r[0:3, 0:3].T * scale
    target[3, 0:3] = pos
    target[3, 3] = 1.0


SHADER = """
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

GLOBALUNIFORMS_DTYPE = np.dtype(
    {
        "names": ["view_proj_mat"],
        "formats": [np.dtype((np.float32, (4, 4)))],
        "offsets": [0],
        "itemsize": 64,
    }
)


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


def fill_cubes(buff: NDArray, rows: int, cols: int):
    uidx = 0
    frame = 120
    pos = np.array([0.0, 0.0, -2.0], dtype=np.float32)
    for y in np.linspace(-1.0, 1.0, rows):
        for x in np.linspace(-1.0, 1.0, cols):
            pos[0] = x
            pos[1] = y
            r = 5.0 * ((x**2.0) + (y**2.0)) ** 0.5
            set_transform(
                buff[uidx]["model_mat"],
                [frame * 0.02 + r, frame * 0.03 + r, frame * 0.04],
                0.7 / rows,
                pos,
            )
            buff[uidx]["color"] = (1.0, 1.0, 1.0, 1.0)
            uidx += 1


def runtest():
    app = harness.RenderHarness(os.path.basename(__file__))

    uniform_align = app.device.getLimits2().minUniformBufferOffsetAlignment
    print("Alignment requirement:", uniform_align)
    DRAWUNIFORMS_DTYPE = np.dtype(
        {
            "names": ["model_mat", "color"],
            "formats": [np.dtype((np.float32, (4, 4))), np.dtype((np.float32, 4))],
            "offsets": [0, 64],
            "itemsize": max(uniform_align, 128),
        }
    )

    vbuff, ibuff, vert_layout = app.create_cube_mesh()

    bind_factory = UniformsBindgroup(app.device)
    bind_layout = bind_factory.layout
    app.create_pipeline(
        shader_src=SHADER,
        bind_layouts=[bind_layout, bind_layout],
        vertex_layouts=[vert_layout],
    )

    ROWS = 16
    COLS = 16
    PRIM_COUNT = ROWS * COLS

    global_ubuff = app.device.createBuffer(
        usage=xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=GLOBALUNIFORMS_DTYPE.itemsize,
    )
    cpu_global_ubuff = np.zeros((), dtype=GLOBALUNIFORMS_DTYPE)
    global_ubuff_staging = xg.DataPtr.wrap(cpu_global_ubuff)

    draw_ubuff = app.device.createBuffer(
        usage=xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=DRAWUNIFORMS_DTYPE.itemsize * PRIM_COUNT,
    )
    cpu_draw_ubuff = np.zeros((PRIM_COUNT), dtype=DRAWUNIFORMS_DTYPE)
    draw_ubuff_staging = xg.DataPtr.wrap(cpu_draw_ubuff)

    cpu_global_ubuff["view_proj_mat"] = harness.proj_perspective(
        np.pi / 3.0, 1.0, 0.1, 10.0
    ).T

    fill_cubes(cpu_draw_ubuff, ROWS, COLS)
    queue = app.device.getQueue()
    queue.writeBuffer(global_ubuff, 0, global_ubuff_staging)
    queue.writeBuffer(draw_ubuff, 0, draw_ubuff_staging)

    renderpass = app.begin()
    renderpass.setVertexBuffer(0, vbuff, 0, vbuff.getSize())
    renderpass.setIndexBuffer(ibuff, xg.IndexFormat.Uint16, 0, ibuff.getSize())

    global_bg = bind_factory.bind(global_ubuff)
    renderpass.setBindGroup(0, global_bg, [])

    bgs = []
    doffset = DRAWUNIFORMS_DTYPE.itemsize
    isize = DRAWUNIFORMS_DTYPE.itemsize
    for idx in range(ROWS * COLS):
        bg = bind_factory.bind(draw_ubuff, idx * doffset, isize)
        bgs.append(bg)
        renderpass.setBindGroup(1, bg, [])
        renderpass.drawIndexed(12 * 3, 1, 0, 0, 0)

    app.finish()


if __name__ == "__main__":
    runtest()
