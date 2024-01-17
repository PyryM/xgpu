# xgpu

# xgpu

`xgpu` is a Python 3.7+ binding of [webgpu-native](https://github.com/gfx-rs/wgpu-native) which is auto-generated at build-time and tracks the upstream releases as closely as possible. It is currently in beta, and until it is more mature most users should probably use [wgpu-py](https://github.com/pygfx/wgpu-py).

### Install

Wheels are built for Mac (x86 only), Windows, and Linux for Python 3.7+:
```
pip install xgpu
```

### Motivation

`wgpu-py` is a great project which also binds webgpu-native. The main difference is that `xgpu` adds type hints to nearly every value, and generates data structures at build time rather than at run time so an IDE can auto-complete. `xgpu` also has no abstractions to support different implementations of the WebGPU spec, and no support for anything not implemented in webgpu-native (i.e. the “canvas” mechanism in `wgpu`). Most users should use `wgpu` unless they have specific needs otherwise. 

### Codegen

The code generation was written in Typescript and runs in `bun`. Python users shouldn’t have to touch this.
