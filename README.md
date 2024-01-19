# xgpu

`xgpu` is a Python 3.7+ binding of [webgpu-native](https://github.com/gfx-rs/wgpu-native) which is auto-generated at build-time and tracks the upstream releases as closely as possible. It is currently in beta, and until it is more mature most users should probably use [wgpu-py](https://github.com/pygfx/wgpu-py).

### Install

Wheels are built for Mac (x86 only), Windows, and Linux for Python 3.7+:
```
pip install xgpu
```

### Conventions

`xgpu` is a mostly 1-to-1 binding of `webgpu.h` and `wgpu.h` from `wgpu_native`.

#### General name conventions

* Names keep their formatting from `webgpu.h` but lose `WGPU` prefixes: `WGPUTextureSampleType` -> `TextureSampleType`
* Field names, functions, etc. maintain same camel-case: `WGPUAdapterProperties.vendorName` -> `AdapterProperties.vendorName`
* Enum variants lose prefix: `WGPUTextureUsage_CopySrc` -> `TextureUsage.CopySrc`
  - Names invalid in Python are prefixed with "_": `WGPUBufferUsage_None` -> `BufferUsage._None`

#### Struct constructors

`webgpu.h` requires constructing various structs, for example `WGPUExtent3D`. These can be created in two ways:

```python
# Recommended: create explicit initialized struct (note lowercase name)
extents = xgpu.extent3D(width = 100, height = 100, depthOrArrayLayers = 1)

# Alternative: create 0-initialized struct and then mutate values
extents = xgpu.Extent3D()
extents.width = 100
extents.height = 100
extents.depthOrArrayLayers = 1
```

#### "Member" function calls

As a C API, `webgpu.h` follows typical C convention for member functions, which is to define
them like:

```c
uint32_t wgpuTextureGetHeight(WGPUTexture texture)
```

In `xgpu` these become genuine member functions, e.g.,

```python
class TextureView:
    def getHeight(self) -> int
```

#### Array passing conventions

Some `webgpu.h` functions and structs take arrays using the convention of passing first
the array item count, and then the array pointer, e.g.,

```c
void wgpuQueueSubmit(WGPUQueue queue, size_t commandCount, WGPUCommandBuffer const * commands)

typedef struct WGPUPipelineLayoutDescriptor {
    // ...
    size_t bindGroupLayoutCount;
    WGPUBindGroupLayout const * bindGroupLayouts;
} WGPUPipelineLayoutDescriptor;
```

These are translated to take lists:

```python
class Queue:
  def submit(self, commands: List[CommandBuffer]])

def pipelineLayoutDescriptor(*, bindGroupLayouts: List["BindGroupLayout"])
```

#### Enums and Flags

Enums are translated into `IntEnum`s and inherit all their conveniences:

```python
mode = xgpu.AddressMode.MirrorRepeat
print(int(mode))  # 2
print(mode.name)  # "MirrorRepeat"

mode = xgpu.AddressMode(2)
print(mode.name)  # "ClampToEdge"
```

Some enums are meant to be ORed together into bitflags. These can be combined
in the natural way:

```python
usage = xgpu.BufferUsage.MapRead | xgpu.BufferUsage.CopyDst
print(usage) # prints: 9
```

This works because `IntEnums` inherit all the int methods include bitwise
operations; however, this discards the type information. 
A slightly more annoying but type-safer way is:

```python
usage = xgpu.BufferUsage.MapRead.asflag() | xgpu.BufferUsage.CopyDst
print(usage) # prints: BufferUsage.MapRead | BufferUsage.CopyDst
```

You can also create typed flags from bare ints:
```python
usage = xgpu.BufferUsageFlags(0b1001)
print(usage) # prints: BufferUsage.MapRead | BufferUsage.CopyDst
```

#### Callbacks

Callbacks must be explicitly wrapped in the appropriate callback type:

```python
def my_adapter_cb(status: xgpu.RequestAdapterStatus, gotten: xgpu.Adapter, msg: str):
    print("Got adapter with msg:", msg, ", status:", status.name)
    adapter[0] = gotten

cb = xgpu.RequestAdapterCallback(my_adapter_cb)
```

#### Chained structs

The `webgpu.h` structure chaining convention is represented by `ChainedStruct`, whose
constructor takes a list of `Chainable` and automatically creates the linked chain.

```python
shader_source = """..."""
shader = device.createShaderModule(
    nextInChain=xgpu.ChainedStruct(
      [xgpu.shaderModuleWGSLDescriptor(code=shader_source)]
    ),
    hints=[],
)
```

#### Byte buffers, void pointers

`xgpu` has two translations for `void *`: `VoidPtr` represents a pointer to
opaque data (e.g., a window handle) while `DataPtr` represents a pointer
to a *sized* data structure (e.g., texture data you want to upload). 

For example,
```python
# Note use of VoidPtr.NULL and VoidPtr.raw_cast
surf_desc = xgpu.surfaceDescriptorFromWindowsHWND(
    hinstance=xgpu.VoidPtr.NULL,
    hwnd=xgpu.VoidPtr.raw_cast(self.window_handle),
)

# DataPtr.wrap can wrap anything supporting the 'buffer' interface
bytedata = bytearray(100)
wrapped = xgpu.DataPtr.wrap(bytedata)

queue.writeBuffer(
  buffer=some_buffer, 
  bufferOffset=0,
  data=wrapped
)

# This includes numpy arrays
my_array = np.ones(100, dtype=np.float32)
wrapped = xgpu.DataPtr.wrap(my_array)
```

### Codegen

The code generation was written in Typescript and runs in `bun`. Python users shouldn’t have to touch this.
