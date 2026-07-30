import os
import pathlib
import dace
sdfg = dace.SDFG.from_file(r'cloudsc_variants/lu_solver/lu_solver_python_frontend.sdfg')
sdfg.build_folder = str(pathlib.Path(r'cloudsc_variants/lu_solver/vec_reports/lu_solver_python_frontend/clang_apple_m_series_disabled/build'))
sdfg.compile()
