# Custom Voxtype native fork

The original in-process C API implementation is published as a real GitHub fork:

**[Sipper1236/voxtype-redux-native](https://github.com/Sipper1236/voxtype-redux-native)**, branch `redux-cpp-native`.

The `custom-voxtype/` submodule pins the complete fork source. Initialize it with:

```sh
git submodule update --init custom-voxtype
```

Or clone this adapter repository with `git clone --recurse-submodules ...`.

`native-redux.patch` is a standalone Git-format patch against upstream commit `dc499ad47444ba6ea80d8750aa3581c23120821c`. `upstream.json` records the exact parent and custom commit. The patch includes the native source, feature wiring, configuration change, benchmark helper and fork documentation. The source retains upstream Voxtype's MIT license.

Build/configuration instructions and limitations are in [the fork documentation](../custom-voxtype/docs/parakeet-cpp-redux.md). The helper can be built with:

```sh
cargo build --manifest-path custom-voxtype/Cargo.toml \
  --release --features parakeet-cpp,moonshine --example bench_worker
```

The stock adapter remains the default deployment. This submodule is optional for running the adapter; it is required for reproducing the resident Voxtype backend screening. Benchmarking a custom binary does not install it or switch your active daemon.
