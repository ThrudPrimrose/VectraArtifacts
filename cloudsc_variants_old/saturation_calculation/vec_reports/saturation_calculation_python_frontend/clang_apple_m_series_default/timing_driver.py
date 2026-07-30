import json, pathlib, sys
import numpy as np
import dace
sys.path.insert(0, r'/Users/alexbonsall/Desktop/ETH/Semester_Thesis/VectraArtifacts')
from only_timing_cloudsc_sdfg import make_inputs
sdfg = dace.SDFG.from_file(r'cloudsc_variants/saturation_calculation/saturation_calculation_python_frontend.sdfg')
sdfg.build_folder = str(pathlib.Path(r'cloudsc_variants/saturation_calculation/vec_reports/saturation_calculation_python_frontend/clang_apple_m_series_default/build'))
sdfg.instrument = dace.dtypes.InstrumentationType.Timer
csdfg = sdfg.compile()
args = make_inputs(sdfg)
warmup = 100
repeats = 200
for _ in range(warmup):
    csdfg(**args)
times = []
for _ in range(repeats):
    csdfg(**args)
    report = sdfg.get_latest_report()
    times.append(report.events[0].duration)
print(json.dumps(times))
