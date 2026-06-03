#!/usr/bin/env python3
"""Worked example: build a populated database from scratch.

* Creates a fresh ``./vectra.db``.
* Ingests the per-kernel audit from ``docs/PARALLELIZATION_AUDIT.md``
  into the ``tsvc_2`` suite.
* Registers a 7-CPU mock topology and a mock run grid (all 63 combos x
  every audited kernel) so the plot generators have something to render.

Run::

  python scripts/populate_example.py
  vectra-plot --db ./vectra.db --kind grid-md
  vectra-plot --db ./vectra.db --kind grid-tex --out grid.tex
  vectra-plot --db ./vectra.db --kind audit-md  --out audit.md
"""
import pathlib
import random

from vectra_artifacts.compilers import Compiler, CostModel
from vectra_artifacts.database import (Suite, connect, create_schema, insert_kernel_audit_rows, insert_runs_bulk)
from vectra_artifacts.database.schema import add_cpu_models
from vectra_artifacts.tsvc_audit import parse_audit_markdown, seed_tsvc_2_5

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "vectra.db"
AUDIT_PATH = REPO_ROOT / "docs" / "PARALLELIZATION_AUDIT.md"

# Seven CPU SKUs for the demo grid; replace with real names when a
# measurement run lands.
_DEMO_CPUS = [
    ("intel_xeon", "x86_64-avx512", 512, "Demo: Intel Xeon (AVX-512)."),
    ("amd_epyc", "x86_64-avx2", 256, "Demo: AMD EPYC Milan (AVX2 only)."),
    ("amd_epyc_genoa", "x86_64-avx512", 512, "Demo: AMD EPYC Genoa (Zen 4 AVX-512)."),
    ("arm_grace", "aarch64-neon", 128, "Demo: NVIDIA Grace (Neoverse V2, 128-bit NEON)."),
    ("fugaku_a64fx", "aarch64-sve", 512, "Demo: Fujitsu A64FX (512-bit SVE)."),
    ("ibm_power", "ppc64le-vsx", 128, "Demo: IBM POWER (VSX 128-bit)."),
    ("apple_m_series", "aarch64-neon", 128, "Demo: Apple M-series (NEON 128-bit)."),
]


def main() -> None:
    conn = connect(DB_PATH)
    create_schema(conn)
    add_cpu_models(conn, _DEMO_CPUS)

    if not AUDIT_PATH.exists():
        raise SystemExit(f"missing audit markdown at {AUDIT_PATH}; "
                         "expected docs/PARALLELIZATION_AUDIT.md (run the audit agent first).")
    rows = parse_audit_markdown(AUDIT_PATH)
    n = insert_kernel_audit_rows(conn, Suite.TSVC_2, rows)
    print(f"ingested {n} kernel audit rows into suite=tsvc_2")

    ext_n = seed_tsvc_2_5(conn)
    print(f"seeded {ext_n} extension kernels into suite=tsvc_2_5")

    # Pull the tsvc_2_5 audit rows back out of the DB so the mock-run
    # generator can iterate over them the same way it does for tsvc_2.
    from vectra_artifacts.database.queries import kernel_audit_rows
    ext_rows = kernel_audit_rows(conn, suites=[Suite.TSVC_2_5])

    # Mock run grid: assume each (cpu, compiler, cost_model) successfully
    # vectorizes the kernel iff (a) the kernel is parallel in principle
    # AND (b) the cost-model isn't ``no``. Deterministic so the example
    # plot is reproducible.
    rng = random.Random(0xCAFE)
    mock_runs: list = []
    for cpu_name, _, _, _ in _DEMO_CPUS:
        for compiler in Compiler:
            for cm in CostModel:
                for suite, suite_rows in ((Suite.TSVC_2, rows), (Suite.TSVC_2_5, ext_rows)):
                    for r in suite_rows:
                        parallel = r["parallel_in_principle"].startswith("yes")
                        base = parallel and cm != CostModel.NO
                        # Add some realistic noise: every compiler has a
                        # few kernels it can't vectorize even when the
                        # kernel is parallel-in-principle.
                        flips = rng.random() < 0.05
                        vec = base ^ flips
                        exec_us = rng.uniform(5.0, 500.0)
                        mock_runs.append({
                            "cpu": cpu_name,
                            "compiler": compiler.value,
                            "cost_model": cm.value,
                            "math": False,
                            "suite": suite,
                            "kernel": r["name"],
                            "vectorized": vec,
                            "exec_us": exec_us,
                        })
    n_runs = insert_runs_bulk(conn, mock_runs)
    total_kernels = len(rows) + len(ext_rows)
    print(f"inserted {n_runs} mock run rows "
          f"(7 CPUs x 9 (compiler, cost_model) x {total_kernels} kernels"
          f"  = {len(rows)} tsvc_2 + {len(ext_rows)} tsvc_2_5)")
    print(f"db at {DB_PATH}")


if __name__ == "__main__":
    main()
