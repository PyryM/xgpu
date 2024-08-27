from abc import abstractmethod
from typing import Optional, Tuple, Union

from .. import bindings as xg
from .wrappers import XDevice


class TextureData:
    @property
    @abstractmethod
    def format(self) -> xg.TextureFormat: ...

    @property
    @abstractmethod
    def level_count(self) -> int: ...

    @property
    @abstractmethod
    def extent3D(self) -> xg.Extent3D: ...

    @property
    @abstractmethod
    def dimension(self) -> xg.TextureDimension: ...

    @abstractmethod
    def get_level_data(self, mip: int) -> bytes: ...

    @abstractmethod
    def get_level_info(self, mip: int) -> Tuple[xg.TextureDataLayout, xg.Extent3D]: ...

    def create_texture(
        self,
        device: XDevice,
        usage: Union[xg.TextureUsageFlags, xg.TextureUsage, int],
        mip_count: Optional[int] = None,
        label: Optional[str] = None,
    ) -> xg.Texture:
        flags = usage | xg.TextureUsage.CopyDst  # must have copy dest
        if mip_count is None:
            mip_count = self.level_count
        mip_count = max(1, min(mip_count, self.level_count))
        tex = device.createTexture(
            label=label,
            usage=flags,
            dimension=self.dimension,
            size=self.extent3D,
            format=self.format,
            mipLevelCount=mip_count,
            sampleCount=1,
            viewFormats=[self.format],
        )
        q = device.getQueue()
        for mip_idx in range(mip_count):
            mip_data = self.get_level_data(mip_idx)
            mip_layout, mip_extent = self.get_level_info(mip_idx)
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
