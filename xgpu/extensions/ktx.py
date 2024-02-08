import math
import struct
from enum import IntEnum
from typing import List, Optional, Tuple, Union

from .. import bindings as xg
from ..textureformats import format_layout_info
from .vkformats import VK_FORMAT_TO_XG
from .wrappers import XDevice

# HEADER FORMAT:
# Byte[12] identifier
# UInt32 vkFormat
# UInt32 typeSize
# UInt32 pixelWidth
# UInt32 pixelHeight
# UInt32 pixelDepth
# UInt32 layerCount
# UInt32 faceCount
# UInt32 levelCount
# UInt32 supercompressionScheme

# // Index
# UInt32 dfdByteOffset
# UInt32 dfdByteLength
# UInt32 kvdByteOffset
# UInt32 kvdByteLength
# UInt64 sgdByteOffset
# UInt64 sgdByteLength

HEADER_FORMAT = "12s" + ("<I" * 9) + ("<I" * 4) + ("<Q" * 2)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

LEVEL_INDEX_FORMAT = "<Q<Q<Q"
LEVEL_INDEX_FORMAT_SIZE = struct.calcsize(LEVEL_INDEX_FORMAT)


class KTXCompression(IntEnum):
    Uncompressed = 0
    BasisLZ = 1
    ZStandard = 2
    ZLib = 3


def mip_pixel_size(mip0_size: int, mip: int) -> int:
    return math.floor(mip0_size / (2**mip))


def block_count(pixel_size: int, mip: int, block_size: int) -> int:
    return max(1, math.ceil(mip_pixel_size(pixel_size, mip) / block_size))


class KTXFile:
    def __init__(self, data: bytes):
        self.data = data
        fields = struct.unpack(HEADER_FORMAT, data[0:HEADER_SIZE])
        self.ident: bytes = fields[0]
        if self.ident != bytes(
            [0xAB, 0x4B, 0x54, 0x58, 0x20, 0x32, 0x30, 0xBB, 0x0D, 0x0A, 0x1A, 0x0A]
        ):
            raise ValueError("Invalid identifier for KTX2")
        vkformat = fields[1]
        xgformat = VK_FORMAT_TO_XG.get(vkformat)
        if xgformat is None:
            raise ValueError(f"Unsupported vkformat: {vkformat}")
        info = format_layout_info(xgformat)
        if info is None:
            raise ValueError(f"Texture format {xgformat.name} cannot be written to.")
        (block_footprint, block_size) = info
        self.block_footprint = block_footprint
        self.block_size = block_size
        self.format: xg.TextureFormat = xgformat
        self.type_size: int = fields[2]
        self.width: int = fields[3]
        self.height: int = fields[4]
        self.depth: int = fields[5]
        self.layer_count: int = fields[6]
        self.face_count: int = fields[7]
        self.level_count: int = max(1, fields[8])
        self.compress: KTXCompression = KTXCompression(fields[9])
        if self.compress > 0 and self.compress != KTXCompression.ZStandard:
            raise ValueError(f"Unsupported compression: {self.compress.name}")
        self.dfd_offset: int = fields[10]
        self.dfd_length: int = fields[11]
        self.kvd_offset: int = fields[12]
        self.kvd_length: int = fields[13]
        self.sgd_offset: int = fields[14]
        self.sgd_length: int = fields[15]
        level_index: List[Tuple[int, int, int]] = []
        for idx in range(self.level_count):
            startpos = HEADER_SIZE + idx * LEVEL_INDEX_FORMAT_SIZE
            endpos = startpos + LEVEL_INDEX_FORMAT_SIZE
            (offset, length, ulength) = struct.unpack(
                LEVEL_INDEX_FORMAT, data[startpos:endpos]
            )
            level_index.append((offset, length, ulength))
        # KTX files store levels from smallest mip to base,
        # which is annoying so just reverse the list
        self.level_index: List[Tuple[int, int, int]] = list(reversed(level_index))

    def pixel_extent(self, mip: int) -> Tuple[int, int, int]:
        sx = mip_pixel_size(self.width, mip)
        sy = mip_pixel_size(self.height, mip)
        sz = mip_pixel_size(self.width, mip)
        return sx, sy, sz

    def block_extent(self, mip: int) -> Tuple[int, int, int, int, int, int]:
        (bx, by) = self.block_size
        bz = 1  # no compressed blocks for z?
        sx = block_count(self.width, mip, bx)
        sy = block_count(self.height, mip, by)
        sz = block_count(self.depth, mip, bz)
        return sx, sy, sz, sx * bx, sy * by, sz * bz

    @property
    def dimension(self) -> xg.TextureDimension:
        if self.face_count > 1 or self.layer_count > 0 or self.depth > 0:
            return xg.TextureDimension._3D
        elif self.height > 0:
            return xg.TextureDimension._2D
        else:
            return xg.TextureDimension._1D

    @property
    def depth_or_array_layers(self) -> int:
        return max(1, self.depth) * max(1, self.face_count) * max(1, self.layer_count)

    @property
    def extent3D(self) -> xg.Extent3D:
        return xg.extent3D(
            width=max(1, self.width),
            height=max(1, self.height),
            depthOrArrayLayers=max(1, self.depth_or_array_layers),
        )

    @property
    def view_dimension(self) -> xg.TextureViewDimension:
        if self.face_count == 6 and self.depth == 0 and self.layer_count == 0:
            return xg.TextureViewDimension.Cube
        elif self.face_count == 6 and self.depth == 0 and self.layer_count > 0:
            return xg.TextureViewDimension.CubeArray
        elif self.layer_count > 0 and self.depth == 0:
            return xg.TextureViewDimension._2DArray
        elif self.depth > 0:
            return xg.TextureViewDimension._3D
        elif self.height > 0:
            return xg.TextureViewDimension._2D
        elif (
            self.width > 0
            and self.height == 0
            and self.depth == 0
            and self.layer_count == 0
        ):
            return xg.TextureViewDimension._1D
        else:
            raise ValueError("Not a valid WebGPU texture shape!")

    def _decompress(self, data: bytes) -> bytes:
        if self.compress == KTXCompression.Uncompressed:
            return data
        raise NotImplementedError()

    def get_raw_level(self, idx: int) -> bytes:
        if not (idx >= 0 and idx < len(self.level_index)):
            raise ValueError(f"index OoB: {idx}/{len(self.level_index)}")
        (offset, length, uncompressed_length) = self.level_index[idx]
        return self._decompress(self.data[offset : offset + length])

    def get_level_info(self, mip: int) -> Tuple[xg.TextureDataLayout, xg.Extent3D]:
        bx, by, _bz, px, py, pz = self.block_extent(mip)
        layercount = max(1, pz) * max(1, self.face_count) * max(1, self.layer_count)
        layout = xg.textureDataLayout(
            offset=0, bytesPerRow=bx * self.block_footprint, rowsPerImage=by
        )
        extent = xg.extent3D(
            width=max(1, px), height=max(1, py), depthOrArrayLayers=layercount
        )
        return layout, extent


class KTXLoader:
    def __init__(self, device: XDevice):
        self.device = device

    def load_from_mem(
        self,
        ktx_data: bytes,
        usage: Union[xg.TextureUsageFlags, xg.TextureUsage, int],
        label: Optional[str] = None,
    ) -> xg.Texture:
        flags = usage | xg.TextureUsage.CopyDst  # must have copy dest
        ktxfile = KTXFile(ktx_data)
        tex = self.device.createTexture(
            label=label,
            usage=flags,
            dimension=ktxfile.dimension,
            size=ktxfile.extent3D,
            format=ktxfile.format,
            mipLevelCount=ktxfile.level_count,
            sampleCount=1,
            viewFormats=[ktxfile.format],
        )
        q = self.device.getQueue()
        for mip_idx in range(ktxfile.level_count):
            mip_data = ktxfile.get_raw_level(mip_idx)
            mip_layout, mip_extent = ktxfile.get_level_info(mip_idx)
            texdest = xg.imageCopyTexture(
                texture=tex,
                mipLevel=mip_idx,
                origin=xg.origin3D(x=0, y=0, z=0),
                aspect=xg.TextureAspect.All,
            )
            q.writeTexture(
                destination=texdest,
                data=xg.DataPtr.wrap(mip_data),
                dataLayout=mip_layout,
                writeSize=mip_extent,
            )
        return tex