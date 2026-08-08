import json, pathlib, sys
import numpy as np
import dace
import time
sys.path.insert(0, r'/Users/alexbonsall/Desktop/ETH/Semester_Thesis/VectraArtifacts')
from only_timing_cloudsc_sdfg import make_inputs
from timer_module import InstrumentWithTimer
sdfg = dace.SDFG.from_file(r'cloudsc_variants/ice_supersaturation_adjustment/ice_supersaturation_adjustment_python_frontend.sdfg')
sdfg.build_folder = str(pathlib.Path(r'cloudsc_variants/ice_supersaturation_adjustment/vec_reports/ice_supersaturation_adjustment_python_frontend/gcc_apple_m_series_disabled/build'))
result_name = InstrumentWithTimer().apply_pass(sdfg, {})
csdfg = sdfg.compile()
args = make_inputs(sdfg)
warmup = 100
repeats = 200
args['time_ns'] = np.zeros(1, dtype=np.int64)
for _ in range(warmup):
    csdfg(**args)
times = []
t0 = time.perf_counter_ns()
for _ in range(repeats):
    csdfg(**args)
    times.append(int(args['time_ns'][0]))
t1 = time.perf_counter_ns()
total_ns = t1 - t0
avg_ns_per_call = total_ns / repeats
print(f'avg_ns_per_call: {avg_ns_per_call}', file=sys.stderr)
print(times)
