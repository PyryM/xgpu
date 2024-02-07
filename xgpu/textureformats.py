from typing import Dict, Optional, Tuple

from .bindings import (
    TextureDataLayout,
    TextureFormat,
    textureDataLayout,
)

TEXEL_BLOCK_FOOTPRINTS: Dict[TextureFormat, int] = {
    TextureFormat.R8Unorm: 1,
    TextureFormat.R8Snorm: 1,
    TextureFormat.R8Uint: 1,
    TextureFormat.R8Sint: 1,
    TextureFormat.R16Uint: 2,
    TextureFormat.R16Sint: 2,
    TextureFormat.R16Float: 2,
    TextureFormat.RG8Unorm: 2,
    TextureFormat.RG8Snorm: 2,
    TextureFormat.RG8Uint: 2,
    TextureFormat.RG8Sint: 2,
    TextureFormat.R32Float: 4,
    TextureFormat.R32Uint: 4,
    TextureFormat.R32Sint: 4,
    TextureFormat.RG16Uint: 4,
    TextureFormat.RG16Sint: 4,
    TextureFormat.RG16Float: 4,
    TextureFormat.RGBA8Unorm: 4,
    TextureFormat.RGBA8UnormSrgb: 4,
    TextureFormat.RGBA8Snorm: 4,
    TextureFormat.RGBA8Uint: 4,
    TextureFormat.RGBA8Sint: 4,
    TextureFormat.BGRA8Unorm: 4,
    TextureFormat.BGRA8UnormSrgb: 4,
    TextureFormat.RGB10A2Uint: 4,
    TextureFormat.RGB10A2Unorm: 4,
    TextureFormat.RG11B10Ufloat: 4,
    TextureFormat.RGB9E5Ufloat: 4,
    TextureFormat.RG32Float: 8,
    TextureFormat.RG32Uint: 8,
    TextureFormat.RG32Sint: 8,
    TextureFormat.RGBA16Uint: 8,
    TextureFormat.RGBA16Sint: 8,
    TextureFormat.RGBA16Float: 8,
    TextureFormat.RGBA32Float: 16,
    TextureFormat.RGBA32Uint: 16,
    TextureFormat.RGBA32Sint: 16,
    TextureFormat.Stencil8: 1,
    TextureFormat.Depth16Unorm: 2,
    #   TextureFormat.Depth24Plus: 0, # Cannot be copied
    #   TextureFormat.Depth24PlusStencil8: 0,
    TextureFormat.Depth32Float: 4,
    #  TextureFormat.Depth32FloatStencil8: 4, # Copying this one is weird
    TextureFormat.BC1RGBAUnorm: 8,
    TextureFormat.BC1RGBAUnormSrgb: 8,
    TextureFormat.BC2RGBAUnorm: 16,
    TextureFormat.BC2RGBAUnormSrgb: 16,
    TextureFormat.BC3RGBAUnorm: 16,
    TextureFormat.BC3RGBAUnormSrgb: 16,
    TextureFormat.BC4RUnorm: 8,
    TextureFormat.BC4RSnorm: 8,
    TextureFormat.BC5RGUnorm: 16,
    TextureFormat.BC5RGSnorm: 16,
    TextureFormat.BC6HRGBUfloat: 16,
    TextureFormat.BC6HRGBFloat: 16,
    TextureFormat.BC7RGBAUnorm: 16,
    TextureFormat.BC7RGBAUnormSrgb: 16,
    TextureFormat.ETC2RGB8Unorm: 8,
    TextureFormat.ETC2RGB8UnormSrgb: 8,
    TextureFormat.ETC2RGB8A1Unorm: 8,
    TextureFormat.ETC2RGB8A1UnormSrgb: 8,
    TextureFormat.ETC2RGBA8Unorm: 16,
    TextureFormat.ETC2RGBA8UnormSrgb: 16,
    TextureFormat.EACR11Unorm: 8,
    TextureFormat.EACR11Snorm: 8,
    TextureFormat.EACRG11Unorm: 16,
    TextureFormat.EACRG11Snorm: 16,
    TextureFormat.ASTC4x4Unorm: 16,
    TextureFormat.ASTC4x4UnormSrgb: 16,
    TextureFormat.ASTC5x4Unorm: 16,
    TextureFormat.ASTC5x4UnormSrgb: 16,
    TextureFormat.ASTC5x5Unorm: 16,
    TextureFormat.ASTC5x5UnormSrgb: 16,
    TextureFormat.ASTC6x5Unorm: 16,
    TextureFormat.ASTC6x5UnormSrgb: 16,
    TextureFormat.ASTC6x6Unorm: 16,
    TextureFormat.ASTC6x6UnormSrgb: 16,
    TextureFormat.ASTC8x5Unorm: 16,
    TextureFormat.ASTC8x5UnormSrgb: 16,
    TextureFormat.ASTC8x6Unorm: 16,
    TextureFormat.ASTC8x6UnormSrgb: 16,
    TextureFormat.ASTC8x8Unorm: 16,
    TextureFormat.ASTC8x8UnormSrgb: 16,
    TextureFormat.ASTC10x5Unorm: 16,
    TextureFormat.ASTC10x5UnormSrgb: 16,
    TextureFormat.ASTC10x6Unorm: 16,
    TextureFormat.ASTC10x6UnormSrgb: 16,
    TextureFormat.ASTC10x8Unorm: 16,
    TextureFormat.ASTC10x8UnormSrgb: 16,
    TextureFormat.ASTC10x10Unorm: 16,
    TextureFormat.ASTC10x10UnormSrgb: 16,
    TextureFormat.ASTC12x10Unorm: 16,
    TextureFormat.ASTC12x10UnormSrgb: 16,
    TextureFormat.ASTC12x12Unorm: 16,
    TextureFormat.ASTC12x12UnormSrgb: 16,
}

TEXEL_BLOCK_SIZES: Dict[TextureFormat, Tuple[int, int]] = {
    # All BC formats are 4x4 blocks
    TextureFormat.BC1RGBAUnorm: (4, 4),
    TextureFormat.BC1RGBAUnormSrgb: (4, 4),
    TextureFormat.BC2RGBAUnorm: (4, 4),
    TextureFormat.BC2RGBAUnormSrgb: (4, 4),
    TextureFormat.BC3RGBAUnorm: (4, 4),
    TextureFormat.BC3RGBAUnormSrgb: (4, 4),
    TextureFormat.BC4RUnorm: (4, 4),
    TextureFormat.BC4RSnorm: (4, 4),
    TextureFormat.BC5RGUnorm: (4, 4),
    TextureFormat.BC5RGSnorm: (4, 4),
    TextureFormat.BC6HRGBUfloat: (4, 4),
    TextureFormat.BC6HRGBFloat: (4, 4),
    TextureFormat.BC7RGBAUnorm: (4, 4),
    TextureFormat.BC7RGBAUnormSrgb: (4, 4),
    # All ETC and EAC formats are 4x4 blocks
    TextureFormat.ETC2RGB8Unorm: (4, 4),
    TextureFormat.ETC2RGB8UnormSrgb: (4, 4),
    TextureFormat.ETC2RGB8A1Unorm: (4, 4),
    TextureFormat.ETC2RGB8A1UnormSrgb: (4, 4),
    TextureFormat.ETC2RGBA8Unorm: (4, 4),
    TextureFormat.ETC2RGBA8UnormSrgb: (4, 4),
    TextureFormat.EACR11Unorm: (4, 4),
    TextureFormat.EACR11Snorm: (4, 4),
    TextureFormat.EACRG11Unorm: (4, 4),
    TextureFormat.EACRG11Snorm: (4, 4),
    # ASTC formats are described by the name
    TextureFormat.ASTC4x4Unorm: (4, 4),
    TextureFormat.ASTC4x4UnormSrgb: (4, 4),
    TextureFormat.ASTC5x4Unorm: (5, 4),
    TextureFormat.ASTC5x4UnormSrgb: (5, 4),
    TextureFormat.ASTC5x5Unorm: (5, 5),
    TextureFormat.ASTC5x5UnormSrgb: (5, 5),
    TextureFormat.ASTC6x5Unorm: (6, 5),
    TextureFormat.ASTC6x5UnormSrgb: (6, 5),
    TextureFormat.ASTC6x6Unorm: (6, 6),
    TextureFormat.ASTC6x6UnormSrgb: (6, 6),
    TextureFormat.ASTC8x5Unorm: (8, 5),
    TextureFormat.ASTC8x5UnormSrgb: (8, 5),
    TextureFormat.ASTC8x6Unorm: (8, 6),
    TextureFormat.ASTC8x6UnormSrgb: (8, 6),
    TextureFormat.ASTC8x8Unorm: (8, 8),
    TextureFormat.ASTC8x8UnormSrgb: (8, 8),
    TextureFormat.ASTC10x5Unorm: (10, 5),
    TextureFormat.ASTC10x5UnormSrgb: (10, 5),
    TextureFormat.ASTC10x6Unorm: (10, 6),
    TextureFormat.ASTC10x6UnormSrgb: (10, 6),
    TextureFormat.ASTC10x8Unorm: (10, 8),
    TextureFormat.ASTC10x8UnormSrgb: (10, 8),
    TextureFormat.ASTC10x10Unorm: (10, 10),
    TextureFormat.ASTC10x10UnormSrgb: (10, 10),
    TextureFormat.ASTC12x10Unorm: (12, 10),
    TextureFormat.ASTC12x10UnormSrgb: (12, 10),
    TextureFormat.ASTC12x12Unorm: (12, 12),
    TextureFormat.ASTC12x12UnormSrgb: (12, 12),
}


def format_layout_info(format: TextureFormat) -> Optional[Tuple[int, Tuple[int, int]]]:
    """Get information about the texel layout of a format
    Returns: (texel block footprint, texel block size) or None if the format cannot be copied
    """
    footprint = TEXEL_BLOCK_FOOTPRINTS.get(format)
    if footprint is None:
        return None
    blocksize = TEXEL_BLOCK_SIZES.get(format, (1, 1))
    return footprint, blocksize


def infer_layout(format: TextureFormat, shape: Tuple[int, int, int]) -> TextureDataLayout:
    # assume no particular alignment requirements
    info = format_layout_info(format)
    if info is None:
        raise ValueError(f"Texture format {format.name} cannot be copied from/to.")
    (block_footprint, (blockwidth, blockheight)) = info
    if (shape[0] % blockwidth != 0) or (shape[1] % blockheight != 0):
        raise ValueError(
            f"Shape {shape} is not a multiple of the block size {(blockwidth,blockheight)}"
        )
    texel_cols = shape[0] // blockwidth
    texel_rows = shape[1] // blockheight
    bytes_per_row = texel_cols * block_footprint
    return textureDataLayout(offset=0, bytesPerRow=bytes_per_row, rowsPerImage=texel_rows)
