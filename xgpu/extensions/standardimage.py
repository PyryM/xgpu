from typing import Tuple

from PIL import Image

from .. import bindings as xg
from .texloader import TextureData


class StandardImageData(TextureData):
    """Represents data for a 'standard' image format (png,jpeg,etc.,
    anything Pillow can open)
    """

    def __init__(self, image: Image.Image):
        self.format = xg.TextureFormat.RGBA8Unorm
        self.dimension = xg.TextureDimension._2D
        self.level_count = 1
        self.image = image.convert("RGBA")
        self.width = self.image.width
        self.height = self.image.height
        self.extent3D = xg.extent3D(
            width=self.image.width, height=self.image.height, depthOrArrayLayers=1
        )
        self.data = self.image.tobytes()

    def get_level_data(self, mip: int) -> bytes:
        assert mip == 0
        return self.data

    def get_level_info(self, mip: int) -> Tuple[xg.TextureDataLayout, xg.Extent3D]:
        assert mip == 0
        layout = xg.textureDataLayout(
            offset=0, bytesPerRow=4 * self.width, rowsPerImage=self.height
        )
        return layout, self.extent3D


def open_image(fn: str) -> StandardImageData:
    return StandardImageData(Image.open(fn))
