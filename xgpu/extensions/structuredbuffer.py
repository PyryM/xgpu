from typing import Optional, Union

import numpy as np
from numpy.typing import DTypeLike, NDArray

from .. import bindings as xg
from .wrappers import XDevice


class StructuredBuffer:
    def __init__(
        self,
        device: XDevice,
        dtype: Optional[DTypeLike] = None,
        usage: Union[xg.BufferUsage, xg.BufferUsageFlags, int] = xg.BufferUsage.Uniform,
        count: Optional[int] = None,
        data: Optional[NDArray] = None,
        allocate_cpu: bool = True,
    ):
        self.device = device
        if data is not None:
            self.dtype = data.dtype
            self.data = data
            self.buff = device.createBufferWithData(data=bytes(data), usage=usage)
            self.byte_size = data.nbytes
        else:
            # if you pass in e.g., np.uint32 as a dtype then this makes sure it's
            # ACTUALLY a dtype with a .itemsize
            self.dtype = np.dtype(dtype)
            if allocate_cpu:
                if count is None:
                    self.data = np.zeros((), dtype=dtype)
                    self.byte_size = 0
                else:
                    self.data = np.zeros((count), dtype=dtype)
                    self.byte_size = self.dtype.itemsize * count
                self.buff = device.createBuffer(
                    size=self.data.nbytes, usage=usage | xg.BufferUsage.CopyDst
                )

            else:
                if count is None:
                    count = 1
                self.buff = device.createBuffer(
                    size=self.dtype.itemsize * count, usage=usage
                )
                self.byte_size = self.dtype.itemsize * count

        assert self.buff.isValid()

    def destroy(self) -> None:
        self.buff.destroy()

    def read(self, queue: Optional[xg.Queue] = None) -> NDArray:
        assert self.buff.getSize() == self.byte_size

        if queue is None:
            queue = self.device.getQueue()

        return np.frombuffer(
            self.device.readBufferStaged(self.buff, 0, self.byte_size), dtype=self.dtype
        )

    def update(self, queue: Optional[xg.Queue] = None) -> None:
        if queue is None:
            queue = self.device.getQueue()
        queue.writeBuffer(self.buff, 0, xg.DataPtr.wrap(self.data))
