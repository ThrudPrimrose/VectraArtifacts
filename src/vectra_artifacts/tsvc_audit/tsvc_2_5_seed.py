"""Seed the ``kernels`` table from the structured TSVC-2.5 extension
metadata in :mod:`tsvc_2_5`.

This avoids round-tripping the extension corpus through a markdown
table: the metadata lives next to the kernel sources and is the source
of truth.
"""
import sqlite3
from typing import Iterable

from ..database.schema import Suite
from ..database.populate import insert_kernel_audit_rows


def seed_tsvc_2_5(conn: sqlite3.Connection) -> int:
    """Ingest every kernel from :mod:`tsvc_2_5` into the
    ``kernels`` table under :attr:`Suite.TSVC_2_5`.

    Idempotent: re-running updates each row in place. Returns the
    number of rows written.
    """
    from tsvc_2_5 import kernel_table

    rows: Iterable[dict] = (
        {
            "name": r.name,
            "category": r.category,
            "tsvc_comment": "",  # extension corpus -- no upstream TSVC comment
            "loop_shape": r.description,
            "parallel_in_principle": "yes-with-runtime-check",
            "blocking_factor": r.blocking_factor,
            "dace_status": "(pending measurement)",
            "notes": "",
        } for r in kernel_table())
    return insert_kernel_audit_rows(conn, Suite.TSVC_2_5, list(rows))
