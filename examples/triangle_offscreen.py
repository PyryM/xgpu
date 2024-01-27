"""
Draw a triangle (offscreen), read it back, and save to png

Largely ported from wgpu-py (BSD2):
https://github.com/pygfx/wgpu-py/blob/main/examples/triangle.py

"""

import time

from PIL import Image

import xgpu as xg
from xgpu.extensions import XDevice
from xgpu.helpers import simple_startup

shader_source = """
struct VertexInput {
    @builtin(vertex_index) vertex_index : u32,
};
struct VertexOutput {
    @location(0) color : vec4f,
    @builtin(position) pos: vec4f,
};

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var positions = array<vec2f, 3>(
        vec2f(0.0, -0.5),
        vec2f(0.5, 0.5),
        vec2f(-0.5, 0.75),
    );
    var colors = array<vec3f, 3>(  // srgb colors
        vec3f(1.0, 1.0, 0.0),
        vec3f(1.0, 0.0, 1.0),
        vec3f(0.0, 1.0, 1.0),
    );
    let index = i32(in.vertex_index);
    var out: VertexOutput;
    out.pos = vec4f(positions[index], 0.0, 1.0);
    out.color = vec4f(colors[index], 1.0);
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let physical_color = pow(in.color.rgb, vec3f(2.2));  // gamma correct
    return vec4f(physical_color, in.color.a);
}
"""


def main():
    t0 = time.time()
    _instance, _adapter, device, _surface = simple_startup()
    dt = time.time() - t0
    print(f"Took: {dt}")
    return _main(device)


def write_image(filename: str, data: bytes, size: tuple[int, int]):
    img = Image.frombytes("RGBA", size, data)
    img.save(filename)


def _main(device: XDevice):
    WIDTH = 1024
    HEIGHT = 1024

    shader = device.createWGSLShaderModule(code=shader_source)
    layout = device.createPipelineLayout(bindGroupLayouts=[])

    color_tex = device.createTexture(
        usage=xg.TextureUsage.RenderAttachment | xg.TextureUsage.CopySrc,
        size=xg.extent3D(width=WIDTH, height=HEIGHT, depthOrArrayLayers=1),
        format=xg.TextureFormat.RGBA8Unorm,
        viewFormats=[xg.TextureFormat.RGBA8Unorm],
    )

    primitive = xg.primitiveState(
        topology=xg.PrimitiveTopology.TriangleList,
        stripIndexFormat=xg.IndexFormat.Undefined,
    )
    vertex = xg.vertexState(module=shader, entryPoint="vs_main", constants=[], buffers=[])
    color_target = xg.colorTargetState(
        format=xg.TextureFormat.RGBA8Unorm,
        writeMask=xg.ColorWriteMask.All,
    )
    multisample = xg.multisampleState()
    fragment = xg.fragmentState(
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
        format=xg.TextureFormat.RGBA8Unorm,
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

    command_encoder = device.createCommandEncoder()

    render_pass = command_encoder.beginRenderPass(colorAttachments=[color_attachment])

    render_pass.setPipeline(render_pipeline)
    render_pass.draw(3, 1, 0, 0)
    render_pass.end()

    device.getQueue().submit([command_encoder.finish()])

    FILENAME = "test.png"
    texdata = device.readRGBATexture(color_tex)
    print("Tex data size:", len(texdata))
    write_image(FILENAME, texdata, (WIDTH, HEIGHT))
    print(f"Done: saved to {FILENAME}")


if __name__ == "__main__":
    main()
