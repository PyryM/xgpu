"""
Example use of the wgpu API to draw a triangle.

Largely ported from wgpu-py (BSD2):
https://github.com/pygfx/wgpu-py/blob/main/examples/triangle.py

"""

import glfw_window

import webgoo as wg
from webgoo.conveniences import get_adapter, get_device

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

def main():
    WIDTH = 1024
    HEIGHT = 1024

    window = glfw_window.GLFWWindow(WIDTH, HEIGHT, "woo")

    instance = wg.createInstance()
    surface = window.get_surface(instance)
    (adapter, _) = get_adapter(instance, wg.PowerPreference.HighPerformance, surface)
    device = get_device(adapter)

    window.configure_surface(device)

    shader = device.createShaderModule(
        nextInChain=wg.ChainedStruct(
            [wg.shaderModuleWGSLDescriptor(code=shader_source)]
        ),
        hints=[],
    )

    layout = device.createPipelineLayout(bindGroupLayouts=[])

    REPLACE = wg.blendComponent(
        srcFactor=wg.BlendFactor.One,
        dstFactor=wg.BlendFactor.Zero,
        operation=wg.BlendOperation.Add,
    )

    primitive = wg.primitiveState(
        topology=wg.PrimitiveTopology.TriangleList,
        stripIndexFormat=wg.IndexFormat.Undefined,
        frontFace=wg.FrontFace.CCW,
        cullMode=wg.CullMode._None,
    )
    vertex = wg.vertexState(
        module=shader, entryPoint="vs_main", constants=[], buffers=[]
    )
    color_target = wg.colorTargetState(
        format=wg.TextureFormat.RGBA8Unorm,
        blend=wg.blendState(color=REPLACE, alpha=REPLACE),
        writeMask=wg.ColorWriteMask.All,
    )
    multisample = wg.multisampleState()
    fragment = wg.fragmentState(
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

    surf_tex = wg.SurfaceTexture()

    while window.poll():
        command_encoder = device.createCommandEncoder()

        surface.getCurrentTexture(surf_tex)
        print("Tex status?", surf_tex.status.name)

        color_view = surf_tex.texture.createView(
            format = wg.TextureFormat.RGBA8Unorm,
            dimension=wg.TextureViewDimension._2D,
            mipLevelCount=1,
            arrayLayerCount=1
        )

        color_attachment = wg.renderPassColorAttachment(
            view=color_view,
            loadOp=wg.LoadOp.Clear,
            storeOp=wg.StoreOp.Store,
            clearValue=wg.color(r=0.5, g=0.5, b=0.5, a=1.0),
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
