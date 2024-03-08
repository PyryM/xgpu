from typing import Tuple

from PIL import Image

from .. import bindings as xg
from .texloader import TextureData


class StandardImageData(TextureData):
    """Represents data for a 'standard' image format (png,jpeg,etc.,
    anything Pillow can open)
    """

    def __init__(self, image: Image.Image):
        self._format = xg.TextureFormat.RGBA8Unorm
        self._dimension = xg.TextureDimension._2D
        self._level_count = 1
        self.image = image.convert("RGBA")
        self.width = self.image.width
        self.height = self.image.height
        self._extent3D = xg.extent3D(
            width=self.image.width, height=self.image.height, depthOrArrayLayers=1
        )
        self.data = self.image.tobytes()

    @property
    def format(self) -> xg.TextureFormat:
        return self._format

    @property
    def level_count(self) -> int:
        return self._level_count

    @property
    def extent3D(self) -> xg.Extent3D:
        return self._extent3D

    @property
    def dimension(self) -> xg.TextureDimension:
        return self._dimension

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
