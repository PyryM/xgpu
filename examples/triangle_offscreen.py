"""
Draw a triangle (offscreen), read it back, and save to png

Largely ported from wgpu-py (BSD2):
https://github.com/pygfx/wgpu-py/blob/main/examples/triangle.py

"""

import time

from PIL import Image

import webgoo as wg
from webgoo.conveniences import get_adapter, get_device, read_rgba_texture

shader_source = """
struct VertexInput {
    @builtin(vertex_index) vertex_index : u32,
};
struct VertexOutput {
    @location(0) color : vec4<f32>,
    @builtin(position) pos: vec4<f32>,
};

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var positions = array<vec2<f32>, 3>(
        vec2<f32>(0.0, -0.5),
        vec2<f32>(0.5, 0.5),
        vec2<f32>(-0.5, 0.75),
    );
    var colors = array<vec3<f32>, 3>(  // srgb colors
        vec3<f32>(1.0, 1.0, 0.0),
        vec3<f32>(1.0, 0.0, 1.0),
        vec3<f32>(0.0, 1.0, 1.0),
    );
    let index = i32(in.vertex_index);
    var out: VertexOutput;
    out.pos = vec4<f32>(positions[index], 0.0, 1.0);
    out.color = vec4<f32>(colors[index], 1.0);
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let physical_color = pow(in.color.rgb, vec3<f32>(2.2));  // gamma correct
    return vec4<f32>(physical_color, in.color.a);
}
"""

def main(power_preference=wg.PowerPreference.HighPerformance):
    t0 = time.time()
    (adapter, _) = get_adapter(instance=None, power=power_preference)
    device = get_device(adapter)
    dt = time.time() - t0
    print(f"Took: {dt}")
    return _main(device)


def write_image(filename: str, data: bytes, size: tuple[int, int]):
    img = Image.frombytes("RGBA", size, data)
    img.save(filename)


def _main(device: wg.Device):
    WIDTH = 1024
    HEIGHT = 1024

    shader = device.createShaderModule(
        nextInChain=wg.ChainedStruct(
            [wg.shaderModuleWGSLDescriptor(code=shader_source)]
        ),
        hints=[],
    )

    layout = device.createPipelineLayout(bindGroupLayouts=[])

    color_tex = device.createTexture(
        usage=wg.TextureUsageFlags(
            [wg.TextureUsage.RenderAttachment, wg.TextureUsage.CopySrc]
        ),
        size=wg.extent3D(width=WIDTH, height=HEIGHT, depthOrArrayLayers=1),
        format=wg.TextureFormat.RGBA8Unorm,
        viewFormats=[wg.TextureFormat.RGBA8Unorm],
    )

    primitive = wg.primitiveState(
        topology=wg.PrimitiveTopology.TriangleList,
        stripIndexFormat=wg.IndexFormat.Undefined,
    )
    vertex = wg.vertexState(
        module=shader, entryPoint="vs_main", constants=[], buffers=[]
    )
    color_target = wg.colorTargetState(
        format=wg.TextureFormat.RGBA8Unorm,
        writeMask=wg.ColorWriteMaskFlags([wg.ColorWriteMask.All]),
    )
    multisample = wg.multisampleState()
    fragment = wg.fragmentState(
        module=shader, entryPoint="fs_main", constants=[], targets=[color_target]
    )

    render_pipeline = device.createRenderPipeline(
        layout=layout,
        vertex=vertex,
        primitive=primitive,
        multisample=multisample,
        fragment=fragment,
    )

    color_view = color_tex.createView(
        format=wg.TextureFormat.RGBA8Unorm,
        dimension=wg.TextureViewDimension._2D,
        mipLevelCount=1,
        arrayLayerCount=1,
        aspect=wg.TextureAspect.All,
    )

    color_attachment = wg.renderPassColorAttachment(
        view=color_view,
        loadOp=wg.LoadOp.Clear,
        storeOp=wg.StoreOp.Store,
        clearValue=wg.color(r=0.5, g=0.5, b=0.5, a=1.0),
    )

    command_encoder = device.createCommandEncoder()

    render_pass = command_encoder.beginRenderPass(colorAttachments=[color_attachment])

    render_pass.setPipeline(render_pipeline)
    render_pass.draw(3, 1, 0, 0)
    render_pass.end()

    device.getQueue().submit([command_encoder.finish()])

    FILENAME = "test.png"
    texdata = read_rgba_texture(device, color_tex)
    print("Tex data size:", len(texdata))
    write_image(FILENAME, texdata, (WIDTH, HEIGHT))
    print(f"Done: saved to {FILENAME}")


if __name__ == "__main__":
    main()