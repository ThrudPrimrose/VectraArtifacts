import os
import pathlib
import dace
sdfg = dace.SDFG.from_file(r'cloudsc_variants/rain_evaporation_abel_boutle/rain_evaporation_abel_boutle_fortran_frontend.sdfg')
sdfg.build_folder = str(pathlib.Path(r'cloudsc_variants/rain_evaporation_abel_boutle/vec_reports/rain_evaporation_abel_boutle_fortran_frontend/clang_apple_m_series_default/build'))
sdfg.compile()
