import os
import pathlib
import dace
sdfg = dace.SDFG.from_file(r'cloudsc_variants/ice_supersaturation_adjustment/ice_supersaturation_adjustment_fortran_frontend.sdfg')
sdfg.build_folder = str(pathlib.Path(r'cloudsc_variants/ice_supersaturation_adjustment/vec_reports/ice_supersaturation_adjustment_fortran_frontend/clang_apple_m_series_default/build'))
sdfg.compile()
