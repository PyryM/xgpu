"""
Example use of the wgpu API to draw a triangle. This example is set up
so it can be run on canvases provided by any backend. Running this file
as a script will use the auto-backend (using either glfw or jupyter).

Largely ported from wgpu-py (BSD2):
https://github.com/pygfx/wgpu-py/blob/main/examples/triangle.py


Similar example in other languages / API's:

* Rust wgpu:
  https://github.com/gfx-rs/wgpu-rs/blob/master/examples/hello-triangle/main.rs
* C wgpu:
  https://github.com/gfx-rs/wgpu/blob/master/examples/triangle/main.c
* Python Vulkan:
  https://github.com/realitix/vulkan/blob/master/example/contribs/example_glfw.py

"""

import time
from typing import Optional

from PIL import Image

import webgoo

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


def get_adapter(power: webgoo.PowerPreference) -> webgoo.Adapter:
    adapter: list[Optional[webgoo.Adapter]] = [None]

    def adapterCB(status: webgoo.RequestAdapterStatus, gotten: webgoo.Adapter, msg: str):
        print("Got adapter with msg:", msg, ", status:", status)
        adapter[0] = gotten

    cb = webgoo.RequestAdapterCallback(adapterCB)

    instance = webgoo.createInstance()
    instance.requestAdapter(
        webgoo.requestAdapterOptions(
            powerPreference=power,
            backendType=webgoo.BackendType.Undefined,
            forceFallbackAdapter=False,
        ),
        cb,
    )

    while adapter[0] is None:
        time.sleep(0.1)

    return adapter[0]


def get_device(adapter: webgoo.Adapter) -> webgoo.Device:
    device: list[Optional[webgoo.Device]] = [None]

    def deviceCB(status: webgoo.RequestDeviceStatus, gotten: webgoo.Device, msg: str):
        print("Got device with msg:", msg, ", status:", status)
        device[0] = gotten

    def deviceLostCB(reason: webgoo.DeviceLostReason, msg: str):
        print("Lost device!:", reason, msg)

    dlcb = webgoo.DeviceLostCallback(deviceLostCB)
    cb = webgoo.RequestDeviceCallback(deviceCB)

    adapter.requestDevice(
        webgoo.deviceDescriptor(
            requiredFeatures=[],
            defaultQueue=webgoo.queueDescriptor(),
            deviceLostCallback=dlcb,
        ),
        cb,
    )

    while device[0] is None:
        time.sleep(0.1)

    return device[0]


def main(power_preference=webgoo.PowerPreference.HighPerformance):
    adapter = get_adapter(power_preference)
    device = get_device(adapter)
    return _main(device)


def _mapped_cb(status):
    print("Mapped?", status)
    if status != webgoo.BufferMapAsyncStatus.Success:
        raise RuntimeError(f"Mapping error! {status}")


mapped_cb = webgoo.BufferMapCallback(_mapped_cb)


def read_buffer(device: webgoo.Device, buffer: webgoo.Buffer, offset: int, size: int):
    buffer.mapAsync(
        webgoo.MapModeFlags([webgoo.MapMode.Read]),
        offset=offset,
        size=size,
        callback=mapped_cb,
    )
    device.poll(True, wrappedSubmissionIndex=None)
    # assume we're now mapped? (seems dicey!)
    mapping = buffer.getMappedRange(0, size)
    return mapping.to_bytes()


def read_texture(device: webgoo.Device, tex: webgoo.Texture, size: tuple[int, int]):
    (w, h) = size
    bytesize = w * h * 4
    # create a staging buffer?
    readbuff = device.createBuffer(
        usage=webgoo.BufferUsageFlags(
            [webgoo.BufferUsage.CopyDst, webgoo.BufferUsage.MapRead]
        ),
        size=bytesize,
        mappedAtCreation=False,
    )
    encoder = device.createCommandEncoder()
    encoder.copyTextureToBuffer(
        source=webgoo.imageCopyTexture(
            texture=tex,
            mipLevel=0,
            origin=webgoo.origin3D(x=0, y=0, z=0),
            aspect=webgoo.TextureAspect.All,
        ),
        destination=webgoo.imageCopyBuffer(
            layout=webgoo.textureDataLayout(offset=0, bytesPerRow=w * 4, rowsPerImage=h),
            buffer=readbuff,
        ),
        copySize=webgoo.extent3D(width=w, height=h, depthOrArrayLayers=1),
    )
    device.getQueue().submit([encoder.finish()])
    return read_buffer(device, readbuff, 0, bytesize)


def write_image(filename: str, data: bytes, size: tuple[int, int]):
    img = Image.frombytes("RGBA", size, data)
    img.save(filename)


def _main(device: webgoo.Device):
    WIDTH = 1024
    HEIGHT = 1024

    shader = device.createShaderModule(
        nextInChain=webgoo.ChainedStruct(
            [webgoo.shaderModuleWGSLDescriptor(code=shader_source)]
        ),
        hints=[],
    )

    layout = device.createPipelineLayout(bindGroupLayouts=[])

    color_tex = device.createTexture(
        usage=webgoo.TextureUsageFlags(
            [webgoo.TextureUsage.RenderAttachment, webgoo.TextureUsage.CopySrc]
        ),
        dimension=webgoo.TextureDimension._2D,
        size=webgoo.extent3D(width=WIDTH, height=HEIGHT, depthOrArrayLayers=1),
        format=webgoo.TextureFormat.RGBA8Unorm,
        mipLevelCount=1,
        sampleCount=1,
        viewFormats=[webgoo.TextureFormat.RGBA8Unorm],
    )

    REPLACE = webgoo.blendComponent(
        srcFactor=webgoo.BlendFactor.One,
        dstFactor=webgoo.BlendFactor.Zero,
        operation=webgoo.BlendOperation.Add,
    )

    primitive = webgoo.primitiveState(
        topology=webgoo.PrimitiveTopology.TriangleList,
        stripIndexFormat=webgoo.IndexFormat.Undefined,
        frontFace=webgoo.FrontFace.CCW,
        cullMode=webgoo.CullMode._None,
    )
    vertex = webgoo.vertexState(
        module=shader, entryPoint="vs_main", constants=[], buffers=[]
    )
    color_target = webgoo.colorTargetState(
        format=webgoo.TextureFormat.RGBA8Unorm,
        blend=webgoo.blendState(color=REPLACE, alpha=REPLACE),
        writeMask=webgoo.ColorWriteMaskFlags([webgoo.ColorWriteMask.All]),
    )
    # Note: this mask is *required* to make it render anything!
    # (TODO: extracting default values from the spec!)
    multisample = webgoo.multisampleState(
        count=1, mask=0xFFFFFFFF, alphaToCoverageEnabled=False
    )
    fragment = webgoo.fragmentState(
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

    color_view = color_tex.createView(
        format=webgoo.TextureFormat.RGBA8Unorm,
        dimension=webgoo.TextureViewDimension._2D,
        baseMipLevel=0,
        mipLevelCount=1,
        baseArrayLayer=0,
        arrayLayerCount=1,
        aspect=webgoo.TextureAspect.All,
    )

    color_attachment = webgoo.renderPassColorAttachment(
        view=color_view,
        loadOp=webgoo.LoadOp.Clear,
        storeOp=webgoo.StoreOp.Store,
        clearValue=webgoo.color(r=0.5, g=0.5, b=0.5, a=1.0),
    )

    command_encoder = device.createCommandEncoder()

    render_pass = command_encoder.beginRenderPass(colorAttachments=[color_attachment])

    render_pass.setPipeline(render_pipeline)
    render_pass.draw(3, 1, 0, 0)
    render_pass.end()

    device.getQueue().submit([command_encoder.finish()])

    # TODO: read back texture?
    texdata = read_texture(device, color_tex, (WIDTH, HEIGHT))
    print("Tex data size:", len(texdata))
    write_image("test.png", texdata, (WIDTH, HEIGHT))
    print("Done!")


if __name__ == "__main__":
    main()
