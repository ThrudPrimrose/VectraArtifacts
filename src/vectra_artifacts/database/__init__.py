"""SQLite-backed storage of kernel metadata + per-(cpu, compiler, cost-model, kernel) run results.

Single file format: a ``vectra.db`` SQLite database with these tables:

* ``suites``        -- the two kernel suites (``tsvc_2``, ``tsvc_2_5``).
* ``cpu_models``    -- CPU SKUs used in the sweep.
* ``compilers``     -- the three supported compilers.
* ``cost_models``   -- the three cost-model presets.
* ``compiler_flags`` -- canonical (compiler, cost-model, math) flag list.
* ``kernels``       -- per-kernel audit row (one row per (suite, name)).
* ``runs``          -- per-(cpu, compiler, cost-model, kernel) run record.

See :mod:`vectra_artifacts.database.schema` for DDL,
:mod:`vectra_artifacts.database.populate` for ingestion helpers, and
:mod:`vectra_artifacts.database.queries` for aggregate queries.
"""
from .schema import (DEFAULT_DB_PATH, SCHEMA_DDL, Suite, connect, create_schema, get_schema_version, seed_static_tables)
from .populate import (insert_kernel_audit_rows, insert_run, insert_runs_bulk, list_suites)
from .queries import (kernel_audit_rows, summary_grid)

__all__ = [
    "DEFAULT_DB_PATH",
    "SCHEMA_DDL",
    "Suite",
    "connect",
    "create_schema",
    "get_schema_version",
    "seed_static_tables",
    "insert_kernel_audit_rows",
    "insert_run",
    "insert_runs_bulk",
    "list_suites",
    "kernel_audit_rows",
    "summary_grid",
]
