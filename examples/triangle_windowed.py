"""
Example use of the wgpu API to draw a triangle.

Largely ported from wgpu-py (BSD2):
https://github.com/pygfx/wgpu-py/blob/main/examples/triangle.py

"""

import xgpu as xg
from xgpu.extensions.glfw_window import GLFWWindow

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


def main() -> None:
    WIDTH = 1024
    HEIGHT = 1024

    window = GLFWWindow(WIDTH, HEIGHT, "woo")

    _instance, adapter, device, surface = xg.extensions.startup(
        surface_src=window.get_surface
    )
    assert surface is not None, "Failed to get surface"

    # Lets list some capabilities of this surface
    surf_caps = surface.getCapabilities(adapter)
    print("==== Surface Caps ====")
    print("Formats:", ", ".join([fmt.name for fmt in surf_caps.formats]))
    print("Present modes:", ", ".join([mode.name for mode in surf_caps.presentModes]))
    print(
        "Composite+alpha modes:", ", ".join([mode.name for mode in surf_caps.alphaModes])
    )

    window_tex_format = xg.TextureFormat.BGRA8Unorm
    # surface.getPreferredFormat(adapter)
    print("Window tex format:", window_tex_format.name)

    window.configure_surface(device, window_tex_format)

    shader = device.createWGSLShaderModule(code=shader_source)
    layout = device.createPipelineLayout(bindGroupLayouts=[])

    REPLACE = xg.blendComponent(
        srcFactor=xg.BlendFactor.One,
        dstFactor=xg.BlendFactor.Zero,
        operation=xg.BlendOperation.Add,
    )

    primitive = xg.primitiveState(
        topology=xg.PrimitiveTopology.TriangleList,
        stripIndexFormat=xg.IndexFormat.Undefined,
    )
    vertex = xg.vertexState(module=shader, entryPoint="vs_main", constants=[], buffers=[])
    color_target = xg.colorTargetState(
        format=window_tex_format,
        blend=xg.blendState(color=REPLACE, alpha=REPLACE),
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
        depthStencil=None,
        multisample=multisample,
        fragment=fragment,
    )

    while window.poll():
        command_encoder = device.createCommandEncoder()

        surf_tex = surface.getCurrentTexture2()

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
        render_pass.draw(3, 1, 0, 0)
        render_pass.end()

        device.getQueue().submit([command_encoder.finish()])
        surface.present()

        color_view.release()
        command_encoder.release()
        render_pass.release()
        surf_tex.texture.release()
    print("Should exit?")


if __name__ == "__main__":
    main()
