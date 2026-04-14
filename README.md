# VectraArtifacts

Benchmark infrastructure for comparing native C++ compiler auto-vectorization against [DaCe](https://github.com/spcl/dace)-generated code across the TSVC-2 loop suite.

## Setup

```bash
pip install -e .        # editable install
pip install dace        # for DaCe backend
```

## Quick Start

```python
from tsvc_2.tsvc_bindings import TSVCLibrary
import numpy as np

lib = TSVCLibrary()  # compiles on first use
```

## Contents

- `compiler_config.py` — shared compiler flags for both C++ and DaCe pipelines
- `tsvc_2/` — 151 TSVC-2 microkernels, split/compile tooling, and Python bindings. See [`tsvc_2/README.md`](tsvc_2/README.md).

## License

TSVC-2 loop suite originates from [UoB-HPC/TSVC_2](https://github.com/UoB-HPC/TSVC_2).