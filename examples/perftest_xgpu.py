"""
Stress test doing a lot of draw calls the naive way (without instancing)
"""

import glfw_window
from examples.example_utils import buffer_layout_entry

import xgpu as xg
from xgpu.conveniences import get_adapter, get_device, create_buffer_with_data

import numpy as np

shader_source = """
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

DRAWUNIFORMS_DTYPE = np.dtype(
    {
        "names": ["model_mat", "color"],
        "formats": [np.dtype((np.float32, (4, 4))), np.dtype((np.float32, 4))],
        "offsets": [0, 64],
        "itemsize": 80,
    }
)

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
    raw_indices = [
        2, 6, 7,
        2, 3, 7,
        0, 4, 5,
        0, 1, 5,
        0, 2, 6,
        0, 4, 6,
        1, 3, 7,
        1, 5, 7,
        0, 2, 3,
        0, 1, 3,
        4, 6, 7,
        4, 5, 7
    ]
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

    # same layout for both global and draw uniforms
    bind_layout = device.createBindGroupLayout(entries=[
        buffer_layout_entry(
            binding=0,
            visibility=xg.ShaderStage.Vertex | xg.ShaderStage.Fragment,
            bind_type=xg.BufferBindingType.Uniform,
        ),
    ])
    pipeline_layout = device.createPipelineLayout(
        bindGroupLayouts=[bind_layout, bind_layout]
    )

    window_tex_format = xg.TextureFormat.BGRA8Unorm
    # surface.getPreferredFormat(adapter)
    print("Window tex format:", window_tex_format.name)

    window.configure_surface(device, window_tex_format)

    shader = device.createShaderModule(
        nextInChain=xg.ChainedStruct([xg.shaderModuleWGSLDescriptor(code=shader_source)]),
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
                        arrayStride=32,
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

    surf_tex = xg.SurfaceTexture()

    ROWS = 100
    COLS = 100
    PRIM_COUNT = ROWS * COLS

    vbuff, ibuff = create_geometry_buffers(device)

    global_ubuff = device.createBuffer(
        usage=xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=GLOBALUNIFORMS_DTYPE.itemsize
    )
    cpu_global_ubuff = np.zeros((), dtype=GLOBALUNIFORMS_DTYPE)
    global_ubuff_staging = xg.DataPtr.wrap(cpu_global_ubuff)

    draw_ubuff = device.createBuffer(
        usage = xg.BufferUsage.Uniform | xg.BufferUsage.CopyDst,
        size=DRAWUNIFORMS_DTYPE.itemsize*PRIM_COUNT
    )
    cpu_draw_ubuff = np.zeros((PRIM_COUNT), dtype=DRAWUNIFORMS_DTYPE)
    draw_ubuff_staging = xg.DataPtr.wrap(cpu_draw_ubuff)

    while window.poll():
        command_encoder = device.createCommandEncoder()

        # TODO: actually calculate uniforms here!

        queue = device.getQueue()
        queue.writeBuffer(global_ubuff, 0, global_ubuff_staging)
        queue.writeBuffer(draw_ubuff, 0, draw_ubuff_staging)

        surface.getCurrentTexture(surf_tex)
        print("Tex status?", surf_tex.status.name)

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

        global_bg = device.createBindGroup(layout=bind_layout, entries=[
            xg.bindGroupEntry(
                binding=0,
                buffer=global_ubuff,
                offset=0,
                size=global_ubuff.getSize(),
            ),
        ])
        render_pass.setBindGroup(0, global_bg, [])

        for drawidx in range(ROWS*COLS):
            draw_bg = device.createBindGroup(layout=bind_layout, entries=[
                xg.bindGroupEntry(
                    binding=0,
                    buffer=draw_ubuff,
                    offset=drawidx*DRAWUNIFORMS_DTYPE.itemsize,
                    size=DRAWUNIFORMS_DTYPE.itemsize,
                ),
            ])
            render_pass.setBindGroup(1, draw_bg, [])
            render_pass.drawIndexed(12*3, 1, 0, 0, 0)
        render_pass.end()

        queue.submit([command_encoder.finish()])
        surface.present()

        color_view.release()
        command_encoder.release()
        render_pass.release()
        surf_tex.texture.release()
    print("Should exit?")


if __name__ == "__main__":
    main()
