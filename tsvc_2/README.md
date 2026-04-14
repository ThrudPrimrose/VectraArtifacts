# TSVC-2 Microkernels

151 loop nests from [TSVC-2](https://github.com/UoB-HPC/TSVC_2), each available as a standalone C++ function and a DaCe `@dace.program`.

## Build

```bash
# Split monolithic sources into per-kernel files
python split_cpp_kernels.py -i tsvc2_core.cpp -o tsvc_cpp_microkernels
python split_dace_kernels.py -i tsvc2_core.py  -o tsvc_dace_microkernels

# Compile (parallel)
python compile_cpp_kernels.py tsvc_cpp_microkernels -j$(nproc)
python compile_dace_kernels.py tsvc_dace_microkernels -j$(nproc)
```

Each C++ kernel is split into `_d` (double) and `_f` (float) variants with `__restrict__` annotations. All variants link into a single shared library.

Both pipelines share compiler flags from `compiler_config.py`. Override with `CXX=clang++` or `EXTRA_FLAGS="-mavx512f"`.

## Python Bindings

`tsvc_bindings.py` wraps the compiled `.so` and exposes every kernel as a Python callable. If the library hasn't been built yet, it runs the split + compile pipeline automatically.

```python
from tsvc_bindings import TSVCLibrary
import numpy as np

lib = TSVCLibrary()  # auto-builds on first use

n = 1024
a = np.random.rand(n)
b = np.random.rand(n)

# Each call returns elapsed nanoseconds
ns = lib.s000_d(a, b, iterations=100, len_1d=n)
# Float variant (auto-casts float64 → float32)
ns = lib.s000_f(a, b, iterations=100, len_1d=n)

# List all available kernels
lib.list_kernels()
```

## Files

| File | Description |
|------|-------------|
| `tsvc2_core.cpp` | All 151 kernels — monolithic C++ source |
| `tsvc2_core.py` | All 151 kernels — DaCe `@dace.program` definitions |
| `split_cpp_kernels.py` | Splits C++ source into per-kernel `_d`/`_f` variants |
| `split_dace_kernels.py` | Splits DaCe source into per-kernel modules |
| `compile_cpp_kernels.py` | Parallel `.cpp` → `.o` → single `.so` pipeline |
| `compile_dace_kernels.py` | Parallel DaCe SDFG compilation pipeline |
| `tsvc_bindings.py` | Python bindings for the compiled C++ shared library |