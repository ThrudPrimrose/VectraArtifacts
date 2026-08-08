import os
import pathlib
import dace
sdfg = dace.SDFG.from_file(r'cloudsc_variants/saturation_calculation/saturation_calculation_python_frontend.sdfg')
sdfg.build_folder = str(pathlib.Path(r'cloudsc_variants/saturation_calculation/vec_reports/saturation_calculation_python_frontend/gcc_apple_m_series_cheap/build'))
sdfg.compile()
