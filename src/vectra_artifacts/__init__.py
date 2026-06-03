"""VectraArtifacts: compiler-vectorization benchmarking infrastructure for
the TSVC-2 loop suite.

Top-level imports expose the public API:

* :class:`vectra_artifacts.compilers.Compiler`,
  :class:`vectra_artifacts.compilers.CostModel`,
  :func:`vectra_artifacts.compilers.get_flags`
* :func:`vectra_artifacts.compilers.source_sh`
* :func:`vectra_artifacts.database.connect`,
  :func:`vectra_artifacts.database.create_schema`
* :func:`vectra_artifacts.plotting.render_grid_markdown`,
  :func:`vectra_artifacts.plotting.render_grid_latex`,
  :func:`vectra_artifacts.plotting.render_kernel_audit_markdown`
* :func:`vectra_artifacts.tsvc_audit.parse_audit_markdown`

See ``docs/`` for the data sources backing each module.
"""
__version__ = "0.2.0"
__url__ = "https://github.com/ThrudPrimrose/VectraArtifacts"
