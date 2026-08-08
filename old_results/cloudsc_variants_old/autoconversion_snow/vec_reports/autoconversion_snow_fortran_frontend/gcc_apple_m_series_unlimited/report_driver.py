import os
import pathlib
import dace
sdfg = dace.SDFG.from_file(r'cloudsc_variants/autoconversion_snow/autoconversion_snow_fortran_frontend.sdfg')
sdfg.build_folder = str(pathlib.Path(r'cloudsc_variants/autoconversion_snow/vec_reports/autoconversion_snow_fortran_frontend/gcc_apple_m_series_unlimited/build'))
sdfg.compile()
