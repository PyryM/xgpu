# webgoo/packaging

- `make build`
  - produces `build/webgoo` which runs the `bun` codegen in docker
  - fetches `wgpu_native` from github releases using Python.
- `cd build && cibuildwheel`
  - Produces wheels from the codegen result.
