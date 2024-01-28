import os
from typing import List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray
from PIL import Image

import xgpu as xg


def default_view(tex: xg.Texture) -> xg.TextureView:
    return tex.createView(
        format=xg.TextureFormat.Undefined,
        dimension=xg.TextureViewDimension.Undefined,
        mipLevelCount=1,
        arrayLayerCount=1,
    )


def parse_args() -> Tuple[str, bool, float]:
    import argparse

    parser = argparse.ArgumentParser(description="Run test harness.")
    parser.add_argument(
        "--snapshots", type=str, help="Snapshot directory", default="snapshots"
    )
    parser.add_argument("--emit", help="Emit (write) snapshot", action="store_true")
    parser.add_argument(
        "--threshold",
        type=float,
        help="Difference threshold (fraction) to fail",
        default=0.05,
    )
    args = parser.parse_args()
    return args.snapshots, args.emit, args.threshold


def write_image(filename: str, data: NDArray):
    img = Image.fromarray(data, mode="RGBA")
    img.save(filename)


def read_image(filename: str) -> NDArray:
    img = Image.open(filename)
    return np.array(img)


def compare_images(a: NDArray, b: NDArray, thresh=6.0) -> float:
    diff = np.sum(np.abs(a.astype(np.float64) - b.astype(np.float64)), axis=2)
    total_diff = np.sum(diff > thresh)
    total_pixels = a.shape[0] * a.shape[1]
    return total_diff / total_pixels


def handle_test_output(test_name: str, output: NDArray):
    snapshot_dir, emit, thresh = parse_args()
    snapshot_filename = os.path.join(snapshot_dir, f"{test_name}.png")
    if emit:
        print(f"[ OK ] Writing snapshot to -> {snapshot_filename}")
        write_image(snapshot_filename, output)
    else:
        print(f"Comparing against snapshot <- {snapshot_filename}")
        snapshot = read_image(snapshot_filename)
        diff = compare_images(snapshot, output)
        if diff > thresh:
            failname = os.path.join(snapshot_dir, f"FAIL_{test_name}.png")
            print("[FAIL] Failing output written to:", failname)
            write_image(failname, output)
            raise RuntimeError(
                f"Output differs by {diff} from snapshot; limit is {thresh}"
            )
        else:
            print(f"[PASS] Output differs by {diff} from snapshot.")


class RenderHarness:
    def __init__(
        self,
        name: str,
        resolution: Tuple[int, int] = (512, 512),
        color_format=xg.TextureFormat.RGBA8Unorm,
        depth_format=xg.TextureFormat.Depth24Plus,
    ):
        self.name = name
        self.width, self.height = resolution
        self.instance, self.adapter, self.device, _surf = xg.helpers.startup()
        texsize = xg.extent3D(width=self.width, height=self.height, depthOrArrayLayers=1)
        self.color_tex = self.device.createTexture(
            usage=xg.TextureUsage.RenderAttachment | xg.TextureUsage.CopySrc,
            dimension=xg.TextureDimension._2D,
            size=texsize,
            format=color_format,
            viewFormats=[color_format],
        )
        self.depth_tex = self.device.createTexture(
            usage=xg.TextureUsage.RenderAttachment,
            dimension=xg.TextureDimension._2D,
            size=texsize,
            format=depth_format,
            viewFormats=[depth_format],
        )

    def create_pipeline(
        self,
        shader_src: str,
        bind_layouts: Optional[List[xg.BindGroupLayout]] = None,
        vertex_layouts: Optional[List[xg.VertexBufferLayout]] = None,
    ):
        device = self.device
        shader = device.createWGSLShaderModule(code=shader_src)
        if bind_layouts is None:
            bind_layouts = []
        layout = device.createPipelineLayout(bindGroupLayouts=bind_layouts)
        self.pipeline_layout = layout

        color_tex = self.color_tex

        primitive = xg.primitiveState(
            topology=xg.PrimitiveTopology.TriangleList,
            stripIndexFormat=xg.IndexFormat.Undefined,
        )
        if vertex_layouts is None:
            vertex_layouts = []
        vertex = xg.vertexState(
            module=shader, entryPoint="vs_main", constants=[], buffers=vertex_layouts
        )
        color_target = xg.colorTargetState(
            format=color_tex.getFormat(),
            writeMask=xg.ColorWriteMask.All,
        )
        multisample = xg.multisampleState()
        fragment = xg.fragmentState(
            module=shader, entryPoint="fs_main", constants=[], targets=[color_target]
        )

        default_stencil = xg.stencilFaceState()
        depthstencil = xg.depthStencilState(
            format=self.depth_tex.getFormat(),
            depthWriteEnabled=True,
            depthCompare=xg.CompareFunction.Less,
            stencilFront=default_stencil,
            stencilBack=default_stencil,
        )

        self.pipeline = device.createRenderPipeline(
            layout=layout,
            vertex=vertex,
            primitive=primitive,
            multisample=multisample,
            fragment=fragment,
            depthStencil=depthstencil,
        )

    def begin(self) -> xg.RenderPassEncoder:
        self.encoder = self.device.createCommandEncoder()

        self.color_view = default_view(self.color_tex)
        color_attachment = xg.renderPassColorAttachment(
            view=self.color_view,
            loadOp=xg.LoadOp.Clear,
            storeOp=xg.StoreOp.Store,
            clearValue=xg.color(r=0.0, g=0.5, b=1.0, a=1.0),
        )
        self.depth_view = default_view(self.depth_tex)
        depth_attachment = xg.renderPassDepthStencilAttachment(
            view=self.depth_view,
            depthStoreOp=xg.StoreOp.Store,
            depthLoadOp=xg.LoadOp.Clear,
            depthClearValue=1.0,
            stencilLoadOp=xg.LoadOp.Undefined,
            stencilStoreOp=xg.StoreOp.Undefined,
        )

        self.renderpass = self.encoder.beginRenderPass(
            colorAttachments=[color_attachment], depthStencilAttachment=depth_attachment
        )
        self.renderpass.setPipeline(self.pipeline)
        return self.renderpass

    def finish(self):
        self.renderpass.end()
        self.device.getQueue().submit([self.encoder.finish()])
        texbytes = self.device.readRGBATexture(self.color_tex)
        self.output = np.frombuffer(texbytes, dtype=np.uint8).reshape(
            (self.height, self.width, -1)
        )
        handle_test_output(self.name, self.output)
